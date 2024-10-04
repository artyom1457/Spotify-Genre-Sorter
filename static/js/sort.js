document.addEventListener("DOMContentLoaded", function () {
  const loadingScreen = document.getElementById("loading-screen");
  const contentContainer = document.getElementById("content-container");
  const songCountElement = document.getElementById("song-count");
  const sortButton = document.getElementById("sort-button");
  const genreContainer = document.getElementById("genre-container");
  const genreList = document.getElementById("genre-list");
  const minCountInput = document.getElementById("min-count");
  const searchInput = document.getElementById("song-search");
  const createPlaylistsButton = document.getElementById("create-playlists");
  const progressBar = document.getElementById("progress-bar");
  const progressContainer = document.getElementById("progress-container");

  let fileId = null; // Variable to store the file ID
  let genreData = {};

  // Function to fetch saved tracks and update the song count
  async function fetchSavedTracks() {
    try {
      const response = await fetch("/fetch_saved_tracks"); // Fetch saved tracks
      const data = await response.json();
      const songCount = data.song_count;
      fileId = data.file_id; // Store the file ID from the server

      songCountElement.textContent = `${songCount} songs saved`;
    } catch (error) {
      console.error("Error fetching saved tracks:", error);
      songCountElement.textContent = "Error fetching song count";
    } finally {
      // Hide the loading screen and show the main content
      loadingScreen.style.display = "none";
      contentContainer.style.display = "block";
    }
  }

  async function sortTracks() {
    if (!fileId) {
      console.error("No file ID found. Cannot sort tracks.");
      return;
    }

    // Show progress bar and hide sort button
    sortButton.style.display = "none";
    progressContainer.style.display = "block";
    progressBar.value = 0;

    try {
      // Start sorting tracks
      const response = await fetch("/start_sorting", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ file_id: fileId }), // Send the file ID to the server
      });

      if (!response.ok) {
        throw new Error(`Failed to start sorting: ${response.statusText}`);
      }

      // Connect to the progress updates
      const eventSource = new EventSource(`/events/${fileId}`);

      eventSource.onmessage = async function (event) {
        const data = JSON.parse(event.data);

        // Update progress bar
        const progressValue = data.percentage;
        progressBar.value = progressValue;

        // If sorting is complete (progress = 100)
        if (data.status === "Completed") {
          eventSource.close();
          progressContainer.style.display = "none";

          // Show genre selection interface
          genreContainer.style.display = "block";

          try {
            // Fetch the genres after sorting is complete
            const genresResponse = await fetch(`/get_genres/${fileId}`);
            if (!genresResponse.ok) {
              throw new Error(
                `Failed to fetch genres: ${genresResponse.statusText}`
              );
            }

            const genresData = await genresResponse.json();
            fileId = genresResponse.file_id;
            genreData = JSON.parse(genresResponse.grouped_tracks);
            populateGenres();

            console.log("Genres:", genresData);
          } catch (error) {
            console.error("Error fetching genres:", error);
          }
        }
      };

      eventSource.onerror = function (error) {
        console.error("Error receiving progress updates:", error);
        eventSource.close();
      };
    } catch (error) {
      console.error("Error sorting tracks:", error);
    }
  }

  // const response = await fetch("/fetch_saved_tracks"); // Fetch saved tracks
  // const data = await response.json();

  // // Update the fileId and genreData with sorted data
  // if (data.grouped_tracks && data.file_id) {
  //   fileId = data.file_id;
  //   genreData = JSON.parse(data.grouped_tracks);
  //   populateGenres(); // Populate genres when sorting is complete
  // }

  // Function to populate genres and counts
  function populateGenres() {
    const genres = genreData.genres;
    const counts = genreData.count;
    const minCount = minCountInput.value;
    const searchWord = searchInput.value.toLowerCase();

    genreList.innerHTML = ""; // Clear existing genres

    const genreArray = Object.keys(genres).map((key) => ({
      genre: genres[key],
      count: counts[key],
    }));

    // Sort the array by count in descending order
    genreArray.sort((a, b) => b.count - a.count);

    genreList.innerHTML = ""; // Clear existing genres

    genreArray.forEach((item) => {
      if (
        item.count >= minCount &&
        item.genre.toLowerCase().includes(searchWord)
      ) {
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = item.genre;
        checkbox.id = `genre-${item.genre}`;
        checkbox.className = "checkbox";

        const label = document.createElement("label");
        label.htmlFor = `genre-${item.genre}`;
        label.textContent = `${item.genre} (${item.count})`;

        const div = document.createElement("div");
        div.classList.add("genre-item");
        div.appendChild(checkbox);
        div.appendChild(label);

        div.addEventListener("click", function () {
          // Toggle checkbox state
          checkbox.checked = !checkbox.checked;

          // Toggle 'checked' class on the container based on checkbox state
          if (checkbox.checked) {
            div.classList.add("checked");
          } else {
            div.classList.remove("checked");
          }
        });

        genreList.appendChild(div);
      }
    });
  }

  // Function to create playlists
  async function createPlaylists() {
    if (!fileId) {
      console.error("No file ID found. Cannot create playlists.");
      return;
    }

    const selectedGenres = Array.from(
      document.querySelectorAll("#genre-list input:checked")
    ).map((input) => input.value);
    const minCount = minCountInput.value;

    try {
      const response = await fetch("/create_playlists", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          file_id: fileId,
          genres: selectedGenres,
        }),
      });

      populateGenres();

      const data = await response.json();
      if (response.status === 200) {
        // Display success message with the created genres
        const createdGenres = data.created_genres;
        displayMessage(
          `Playlists created for genres: ${createdGenres.join(", ")}`,
          "success"
        );
      } else if (response.status === 500) {
        // Display error message with failed genres
        const failedGenres = data.failed_genres;
        displayMessage(
          `Failed to create playlists for genres: ${failedGenres.join(", ")}`,
          "error"
        );
      }
    } catch (error) {
      console.error("Error creating playlists:", error);
      displayMessage("An error occurred while creating playlists.", "error");
    }
  }

  function displayMessage(message, type) {
    const messageBox = document.createElement("div");
    messageBox.className = `message-box ${type}`; // Use different styling for success and error
    messageBox.textContent = message;

    // Append the message box to the body (or another container)
    document.body.appendChild(messageBox);

    // Automatically remove the message after 5 seconds
    setTimeout(() => {
      messageBox.remove();
    }, 5000);
  }

  // Attach event listener to the "Sort" button
  sortButton.addEventListener("click", sortTracks);

  // Attach event listener to the "Create Playlists" button
  createPlaylistsButton.addEventListener("click", createPlaylists);

  minCountInput.addEventListener("input", populateGenres);

  searchInput.addEventListener("input", populateGenres);

  // Initial fetch of saved tracks
  fetchSavedTracks();
});
