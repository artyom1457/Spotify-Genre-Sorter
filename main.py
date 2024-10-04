import threading
import time
from dotenv import load_dotenv
import os
from flask import Blueprint, Flask, copy_current_request_context, redirect, request, session, url_for, render_template, jsonify, stream_with_context, Response
import numpy as np
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler

from collections import defaultdict

import pandas as pd

import tempfile
import json
import uuid
import sys

# Initialize the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'secret_key')

# Spotify API credentials and configuration
client_id = os.getenv('SPOTIPY_CLIENT_ID', '')
client_secret = os.getenv('SPOTIPY_CLIENT_SECRET', '')
redirect_uri = os.getenv('SPOTIPY_REDIRECT_URI', '')
scope = 'playlist-modify-private,playlist-read-private,user-library-read'

temp_files = []

if not (client_id and client_secret and redirect_uri):
    print("the client id and client secret weren't specified")
    sys.exit()

# Spotify OAuth setup
cache_handler = FlaskSessionCacheHandler(session)
sp_oauth = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope=scope,
    cache_handler=cache_handler,
    show_dialog=True
)
sp = Spotify(auth_manager=sp_oauth)

# Define the main Blueprint
main_bp = Blueprint('main', __name__)

# Global state for progress tracking per file ID
progress_data = defaultdict(lambda: {'status': 'Not Started', 'percentage': 0})

DEVELOP = True


def load_tracks_from_file(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)
    

def get_genre(artist_id):
    artist = sp.artist(artist_id)
    genres = artist['genres']

    return genres


def group_by_artists(tracks):
    df = pd.DataFrame([{'id': track['track']['id'], 'artists': [artist["id"] for artist in track['track']['artists']]} for track in tracks])
    artist_songs = df.explode('artists').groupby('artists')['id'].apply(list).reset_index()
    artist_songs.columns = ['artist_id', 'song_ids']

    return artist_songs


def save_tracks_to_file(tracks):
    temp_dir = tempfile.gettempdir()
    file_id = str(uuid.uuid4())
    file_path = os.path.join(temp_dir, f"{file_id}.json")
    
    with open(file_path, 'w') as f:
        json.dump(tracks, f)
    
    temp_files.append(file_path)

    return file_path

def get_all_saved_tracks():
    # Initialize an empty list to hold all saved tracks
    all_tracks = []
    
    if not DEVELOP:
    # Fetch the first page of saved tracks
        results = sp.current_user_saved_tracks(limit=50)  # Adjust limit if needed
        all_tracks.extend(results['items'])

        # Continue fetching the remaining pages
        while results['next']:
            results = sp.next(results)
            all_tracks.extend(results['items'])
    
    else:
        all_tracks = load_tracks_from_file(r"files\saved_songs.json")

    return all_tracks

# Home route
@main_bp.route('/')
def home():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    # return redirect(url_for('main.get_playlists'))
    return render_template('homepage.html')


# Callback route
@main_bp.route('/callback')
def callback():
    sp_oauth.get_access_token(request.args['code'])
    return redirect(url_for('main.home'))


@main_bp.route('/fetch_saved_tracks')
def fetch_saved_tracks():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        return redirect(sp_oauth.get_authorize_url())

    results = get_all_saved_tracks()

    # Save to a temporary file
    file_path = os.path.splitext(os.path.basename(save_tracks_to_file(results)))[0]
    song_count = len(results)
    
    return jsonify({'song_count': song_count, 'file_id': file_path})

@main_bp.route('/start_sorting', methods=['POST'])
def start_sorting():
    file_id = request.json.get('file_id')
    file_path = os.path.join(tempfile.gettempdir(), f"{file_id}.json")
    
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    # Load tracks from file
    tracks = load_tracks_from_file(file_path)
    
    artists_songs = group_by_artists(tracks)

    size = len(artists_songs.index)
    artists_songs['genres'] = [[] for _ in range(len(artists_songs))]
    progress_data[file_id]


    @copy_current_request_context
    def get_genres(file_id,artists_songs):
        global progress_data

        if not DEVELOP:
            for i, (index, row) in enumerate(artists_songs.iterrows()):
                artists_songs.at[index, 'genres'] = get_genre(row['artist_id'])
                progress_data[file_id]['percentage'] = int((i + 1) / size * 100)
                # yield f"data: {json.dumps({'progress': progress})}\n\n"
        else:
            artists_songs = load_tracks_from_file(r"files\temp.json")
        
        file_path = os.path.join(tempfile.gettempdir(), f"{file_id}.json")
        with open(file_path, 'w') as f:
            json.dump(artists_songs, f)

        progress_data[file_id]['status'] = 'Completed'

    # Run sorting in a separate thread
    get_genres_t = threading.Thread(target=get_genres, args = (file_id,artists_songs,))
    get_genres_t.start()

    return jsonify({'message': 'Sorting started'}), 200

@main_bp.route('/events/<file_id>')
def events(file_id):
    if file_id not in progress_data:
        return jsonify({"error": "No sorting operation found for this file ID"}), 404
    
    def generate():
        while progress_data[file_id]['status'] != 'Completed':
            yield f"data: {json.dumps(progress_data[file_id])}\n\n"
            time.sleep(1)
        
        # Send final message to notify completion
        yield f"data: {json.dumps(progress_data[file_id])}\n\n"

        progress_data.pop(file_id, None)

    return Response(generate(), content_type='text/event-stream')


@main_bp.route('/get_genres/<file_id>')
def get_genres(file_id):
    file_path = os.path.join(tempfile.gettempdir(), f"{file_id}.json")
    
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    # Load tracks from file
    artists_songs = pd.DataFrame(json.loads(load_tracks_from_file(file_path)))

    # label each track with its corresponding genre
    labeled_songs = artists_songs.explode('song_ids').groupby('song_ids')['genres'].apply(lambda x: list(set(genre for sublist in x for genre in sublist))).reset_index()

    grouped_tracks = labeled_songs.explode('genres').groupby('genres')['song_ids'].apply(list).reset_index()

    #counting the tracks
    grouped_tracks["count"] = grouped_tracks.agg({"song_ids":lambda x: len(x)})

    # Clean up by deleting the file after sorting
    os.remove(file_path)
    temp_files.remove(file_path)

    file_path = os.path.splitext(os.path.basename(save_tracks_to_file(grouped_tracks.to_json())))[0]

    return jsonify({'grouped_tracks': grouped_tracks[['genres',"count"]].to_json(), 'file_id': file_path})


@main_bp.route("/create_playlists", methods=['POST'])
def create_playlists():
    file_id = request.json.get('file_id')
    requested_genres = request.json.get('genres')

    file_path = os.path.join(tempfile.gettempdir(), f"{file_id}.json")
    
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    
    saved_genres = pd.DataFrame(json.loads(load_tracks_from_file(file_path)))
    user_id = sp.me()['id']

    created_genres = []
    failed_playlists = []  # List to store genres that failed
    track_batch_size = 100  # Maximum number of tracks allowed per request

    for genre in requested_genres:
        playlist_name = f'{genre} GenreSorter'
        track_ids = saved_genres.loc[saved_genres['genres'] == genre]['song_ids'].iloc[0]  # Accessing the track_ids safely

        try:
            # Create the playlist
            playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=False, description='My custom playlist')
            
            playlist_id = playlist['id']

            # Add tracks in batches of 100
            for i in range(0, len(track_ids), track_batch_size):
                batch = track_ids[i:i + track_batch_size]
                sp.playlist_add_items(playlist_id=playlist_id, items=batch)

            created_genres.append(genre)

        except Exception as e:
            # Add the genre to the failed list in case of any exception
            failed_playlists.append(genre)
            print(f"Failed to create playlist for genre: {genre}, Error: {e}")


    # Check if there are any failed playlists
    if failed_playlists:
        return jsonify({'message': 'Some playlists failed to be created', 'failed_genres': failed_playlists}), 500
    else:
        return jsonify({'message': 'Playlists created successfully', 'created_genres': created_genres}), 200


# Clean up session data when navigating back to the home page
@main_bp.route('/clear_session')
def clear_session():
    session.pop('saved_tracks', None)
    return redirect(url_for('main.home'))



# Sort route
@main_bp.route('/sort_page')
def sort_page():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        return redirect(sp_oauth.get_authorize_url())
    
    return render_template('sort.html')



# Get playlists route
@main_bp.route('/playlists')
def playlists():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        return redirect(sp_oauth.get_authorize_url())


    return render_template('playlists.html')

@main_bp.route('/get_playlists')
def get_playlists():
    # Check if the token is valid
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        return redirect(sp_oauth.get_authorize_url())

    # Get query parameters for pagination
    offset = int(request.args.get('offset', 0))  # Default to 0 if not provided
    limit = request.args.get('limit', None)       # Default to None if not provided
    limit = int(limit) if limit else None

    owner_id = sp.current_user()['id']

    # Fetch all playlists and filter by owner ID
    playlists = sp.current_user_playlists()
    filtered_playlists = [
        {"name": pl['name'], "url": pl['external_urls']['spotify']}
        for pl in playlists['items']
        if pl['owner']['id'] == owner_id
    ]

    # Apply pagination to the filtered playlists
    paginated_playlists = filtered_playlists[offset:offset + limit] if limit is not None else filtered_playlists[offset:]

    # Return playlists as JSON
    return jsonify({'playlists': paginated_playlists})


# Logout route
@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.home'))

# Register the Blueprint
app.register_blueprint(main_bp)


def delete_temp_files():
    global temp_files

    for file in temp_files:
        try:
            os.remove(file)
        except Exception as e:
            print(f"{file} couldn't be deleted")
            print(e)



# Main entry point
if __name__ == '__main__':
    try:
        app.run(debug=True)
    finally:
        # delete all temp files created when program ends
        delete_temp_files()