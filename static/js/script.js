document.addEventListener("DOMContentLoaded", () => {
  let offset = 0;
  const limit = 20;
  const playlistList = document.getElementById("playlist-list");
  const loadMoreBtn = document.getElementById("load-more-btn");

  function fetchPlaylists() {
    fetch(`/get_playlists?offset=${offset}&limit=${limit}`)
      .then((response) => response.json())
      .then((data) => {
        data.playlists.forEach((playlist) => {
          const listItem = document.createElement("li");
          listItem.className = "playlist-item";
          listItem.innerHTML = `<a href="${playlist.url}" target="_blank">${playlist.name}</a>`;
          playlistList.appendChild(listItem);
        });

        if (data.playlists.length < limit) {
          loadMoreBtn.style.display = "none";
        }

        offset += limit;
      })
      .catch((error) => console.error("Error fetching playlists:", error));
  }

  fetchPlaylists();

  loadMoreBtn.addEventListener("click", fetchPlaylists);
});
