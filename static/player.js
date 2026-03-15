// Singleton audio player
// Exported as `window.Player` so app.js can interact with it.

const audio = document.getElementById("audio-el");
const bar = document.getElementById("player-bar");
const btnPlay = document.getElementById("btn-play");
const btnPrev = document.getElementById("btn-prev");
const btnNext = document.getElementById("btn-next");
const scrubber = document.getElementById("scrubber");
const timeCurrent = document.getElementById("time-current");
const timeTotal = document.getElementById("time-total");
const speedSelect = document.getElementById("speed-select");
const playerTitle = document.getElementById("player-title");
const playerTrack = document.getElementById("player-track");
const playerCover = document.getElementById("player-cover");

let state = {
  book: null,       // book detail object
  trackIndex: 0,
  isScrubbing: false,
  saveTimer: null,
};

export function fmt(secs) {
  if (!isFinite(secs) || secs < 0) return "0:00";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

function updatePlayBtn() {
  btnPlay.innerHTML = audio.paused ? "&#9654;" : "&#9646;&#9646;";
}

function updateProgress() {
  if (state.isScrubbing) return;
  const dur = audio.duration;
  const cur = audio.currentTime;
  timeCurrent.textContent = fmt(cur);
  timeTotal.textContent = fmt(dur);
  if (dur > 0) {
    scrubber.value = (cur / dur) * 100;
  }
}

function updateTrackDisplay() {
  if (!state.book) return;
  const files = state.book.files || [];
  const track = files[state.trackIndex];
  playerTitle.textContent = state.book.title || "Unknown";
  playerTrack.textContent = track
    ? `Track ${state.trackIndex + 1} / ${files.length}`
    : "";

  // Update track list active state in detail view if visible
  document.querySelectorAll(".track-item").forEach((el, i) => {
    el.classList.toggle("active", i === state.trackIndex);
  });

  updateMediaSession();
}

function updateMediaSession() {
  if (!("mediaSession" in navigator) || !state.book) return;
  const files = state.book.files || [];

  navigator.mediaSession.metadata = new MediaMetadata({
    title: state.book.title || "Unknown",
    artist: state.book.author || "",
    album: state.book.series || "",
    artwork: state.book.has_cover
      ? [{ src: `/api/cover/${state.book.book_id}`, sizes: "256x256", type: "image/jpeg" }]
      : [],
  });

  navigator.mediaSession.setActionHandler("play",  () => audio.play().catch(() => {}));
  navigator.mediaSession.setActionHandler("pause", () => audio.pause());
  navigator.mediaSession.setActionHandler("previoustrack", () => {
    if (audio.currentTime > 5) audio.currentTime = 0;
    else if (state.trackIndex > 0) loadTrack(state.trackIndex - 1, 0);
  });
  navigator.mediaSession.setActionHandler("nexttrack", () => {
    if (state.trackIndex < files.length - 1) loadTrack(state.trackIndex + 1, 0);
  });
  navigator.mediaSession.setActionHandler("seekbackward", details => {
    audio.currentTime = Math.max(0, audio.currentTime - (details.seekOffset || 10));
  });
  navigator.mediaSession.setActionHandler("seekforward", details => {
    audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + (details.seekOffset || 10));
  });
  try {
    navigator.mediaSession.setActionHandler("seekto", details => {
      if (details.seekTime != null) audio.currentTime = details.seekTime;
    });
  } catch (_) {} // not supported in all browsers
}

function loadTrack(index, seekTo = 0, autoplay = true) {
  if (!state.book) return;
  const files = state.book.files || [];
  if (index < 0 || index >= files.length) return;
  state.trackIndex = index;
  audio.src = `/api/stream/${state.book.book_id}/${index}`;
  audio.currentTime = 0;
  audio.load();
  if (seekTo > 0) {
    const onCanPlay = () => {
      audio.currentTime = seekTo;
      audio.removeEventListener("canplay", onCanPlay);
    };
    audio.addEventListener("canplay", onCanPlay);
  }
  if (autoplay) audio.play().catch(() => {});
  updateTrackDisplay();
}

function savePosition() {
  if (!state.book) return;
  fetch(`/api/position/${state.book.book_id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_index: state.trackIndex,
      time_seconds: audio.currentTime,
    }),
  }).catch(() => {});
}

function schedulePositionSave() {
  if (state.saveTimer) clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(savePosition, 5000);
}

// ── Event wiring ──────────────────────────────────────────────────

audio.addEventListener("play", updatePlayBtn);
audio.addEventListener("pause", () => { updatePlayBtn(); savePosition(); });
audio.addEventListener("timeupdate", () => {
  updateProgress();
  schedulePositionSave();
});
audio.addEventListener("ended", () => {
  const files = state.book?.files || [];
  savePosition();
  if (state.trackIndex < files.length - 1) {
    loadTrack(state.trackIndex + 1, 0);
  }
});
audio.addEventListener("error", () => {
  console.error("Audio error on track", state.trackIndex);
});

btnPlay.addEventListener("click", () => {
  if (audio.paused) audio.play().catch(() => {});
  else audio.pause();
});

btnPrev.addEventListener("click", () => {
  if (audio.currentTime > 5) {
    audio.currentTime = 0;
  } else if (state.trackIndex > 0) {
    loadTrack(state.trackIndex - 1, 0);
  }
});

btnNext.addEventListener("click", () => {
  const files = state.book?.files || [];
  if (state.trackIndex < files.length - 1) {
    loadTrack(state.trackIndex + 1, 0);
  }
});

scrubber.addEventListener("mousedown", () => { state.isScrubbing = true; });
scrubber.addEventListener("touchstart", () => { state.isScrubbing = true; });
scrubber.addEventListener("input", () => {
  const dur = audio.duration;
  if (dur > 0) {
    const t = (parseFloat(scrubber.value) / 100) * dur;
    timeCurrent.textContent = fmt(t);
  }
});
scrubber.addEventListener("change", () => {
  state.isScrubbing = false;
  const dur = audio.duration;
  if (dur > 0) {
    audio.currentTime = (parseFloat(scrubber.value) / 100) * dur;
  }
  savePosition();
});

speedSelect.addEventListener("change", () => {
  audio.playbackRate = parseFloat(speedSelect.value);
});

// ── Public API ─────────────────────────────────────────────────────

async function loadBook(book, forceTrackIndex = null, { paused = false } = {}) {
  state.book = book;

  // Remember last-played book across page reloads
  try { localStorage.setItem("bookthing.lastBook", book.book_id); } catch (_) {}

  // Show cover in player bar
  if (book.has_cover) {
    playerCover.src = `/api/cover/${book.book_id}`;
    playerCover.hidden = false;
  } else {
    playerCover.hidden = true;
  }

  bar.classList.remove("hidden");
  updateTrackDisplay();

  if (forceTrackIndex !== null) {
    loadTrack(forceTrackIndex, 0, !paused);
    return;
  }

  // Restore saved position from server
  let startIndex = 0;
  let startTime = 0;
  try {
    const res = await fetch(`/api/position/${book.book_id}`);
    if (res.ok) {
      const pos = await res.json();
      startIndex = pos.file_index || 0;
      startTime = pos.time_seconds || 0;
    }
  } catch (_) {}

  loadTrack(startIndex, startTime, !paused);
}

function jumpToTrack(index) {
  loadTrack(index, 0);
}

function currentBookId() {
  return state.book?.book_id ?? null;
}

// Clicking the player info area navigates to the current book's detail page
document.getElementById("player-bar").querySelector(".player-info").addEventListener("click", () => {
  if (!state.book) return;
  window.navigate?.(`/book/${state.book.book_id}`);
});

window.Player = { loadBook, jumpToTrack, currentBookId };
