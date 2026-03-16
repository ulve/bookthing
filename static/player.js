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
  timeMode: 1,      // 0=part left, 1=book left, 2=percent
  lastChapterIdx: -1,
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

function secondsToTrackSeek(startSeconds, fileDurations) {
  let remaining = startSeconds;
  for (let i = 0; i < fileDurations.length; i++) {
    if (remaining <= fileDurations[i]) return { trackIndex: i, seekTo: remaining };
    remaining -= fileDurations[i];
  }
  return { trackIndex: Math.max(0, fileDurations.length - 1), seekTo: 0 };
}

function currentChapterIndex() {
  const chapters = state.book?.chapters;
  if (!chapters?.length) return -1;
  const durs = state.book.file_durations || [];
  const elapsed = durs.slice(0, state.trackIndex).reduce((a, v) => a + v, 0) + (audio.currentTime || 0);
  let idx = 0;
  for (let i = 0; i < chapters.length; i++) {
    if (chapters[i].start <= elapsed) idx = i;
    else break;
  }
  return idx;
}

function bookProgressInfo() {
  const durs = state.book?.file_durations || [];
  const bookTotal = durs.reduce((a, v) => a + v, 0);
  const elapsed = durs.slice(0, state.trackIndex).reduce((a, v) => a + v, 0) + (audio.currentTime || 0);
  return { bookTotal, elapsed };
}

function updateProgress() {
  if (state.isScrubbing) return;
  const dur = audio.duration;
  const cur = audio.currentTime;
  timeCurrent.textContent = fmt(cur);
  if (dur > 0) scrubber.value = (cur / dur) * 100;

  // Refresh chapter name if it has changed (chapters can change mid-track for single M4B)
  if (state.book?.chapters?.length) updateTrackDisplay();

  const { bookTotal, elapsed } = bookProgressInfo();

  if (state.timeMode === 1 && bookTotal > 0) {
    const remaining = Math.max(0, bookTotal - elapsed);
    timeTotal.textContent = `-${fmt(remaining)}`;
  } else if (state.timeMode === 2 && bookTotal > 0) {
    const pct = Math.min(100, Math.round((elapsed / bookTotal) * 100));
    timeTotal.textContent = `${pct}%`;
  } else if (isFinite(dur) && dur > 0) {
    timeTotal.textContent = `-${fmt(dur - cur)}`;
  } else {
    timeTotal.textContent = fmt(dur);
  }
}

function updateTrackDisplay() {
  if (!state.book) return;
  const files = state.book.files || [];
  const chapters = state.book.chapters;
  playerTitle.textContent = state.book.title || "Unknown";

  if (chapters?.length) {
    const idx = currentChapterIndex();
    if (idx !== state.lastChapterIdx) {
      state.lastChapterIdx = idx;
      playerTrack.textContent = chapters[idx]?.title ?? "";
      document.querySelectorAll(".chapter-item").forEach((el, i) => {
        el.classList.toggle("active", i === idx);
      });
    }
  } else {
    const track = files[state.trackIndex];
    playerTrack.textContent = track ? `Track ${state.trackIndex + 1} / ${files.length}` : "";
    document.querySelectorAll(".track-item").forEach((el, i) => {
      el.classList.toggle("active", i === state.trackIndex);
    });
  }

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
    window.clientLog?.("info", "track advance", { book_id: state.book?.book_id, track: state.trackIndex + 1 });
    loadTrack(state.trackIndex + 1, 0);
  }
});
audio.addEventListener("error", () => {
  window.clientLog?.("error", "audio error", {
    book_id: state.book?.book_id,
    track: state.trackIndex,
    error: audio.error?.message,
  });
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
    const { bookTotal } = bookProgressInfo();
    if (state.timeMode === 1 && bookTotal > 0) {
      const durs = state.book?.file_durations || [];
      const baseElapsed = durs.slice(0, state.trackIndex).reduce((a, v) => a + v, 0);
      const remaining = Math.max(0, bookTotal - baseElapsed - t);
      timeTotal.textContent = `-${fmt(remaining)}`;
    } else if (state.timeMode === 2 && bookTotal > 0) {
      const durs = state.book?.file_durations || [];
      const baseElapsed = durs.slice(0, state.trackIndex).reduce((a, v) => a + v, 0);
      const pct = Math.min(100, Math.round(((baseElapsed + t) / bookTotal) * 100));
      timeTotal.textContent = `${pct}%`;
    } else {
      timeTotal.textContent = `-${fmt(dur - t)}`;
    }
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

timeTotal.addEventListener("click", () => {
  state.timeMode = (state.timeMode + 1) % 3;
  updateProgress();
});

timeTotal.title = "Click to cycle: part left / book left / percent";

// ── Public API ─────────────────────────────────────────────────────

async function loadBook(book, forceTrackIndex = null, { paused = false, startAtSeconds = null } = {}) {
  window.clientLog?.("info", "load book", { book_id: book.book_id, title: book.title });
  state.book = book;
  state.lastChapterIdx = -1;

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

  if (startAtSeconds !== null) {
    const { trackIndex, seekTo } = secondsToTrackSeek(startAtSeconds, book.file_durations || []);
    loadTrack(trackIndex, seekTo, !paused);
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

function jumpToChapter(startSeconds) {
  const { trackIndex, seekTo } = secondsToTrackSeek(startSeconds, state.book?.file_durations || []);
  loadTrack(trackIndex, seekTo);
}

function currentBookId() {
  return state.book?.book_id ?? null;
}

// Clicking the player info area navigates to the current book's detail page
document.getElementById("player-bar").querySelector(".player-info").addEventListener("click", () => {
  if (!state.book) return;
  window.navigate?.(`/book/${state.book.book_id}`);
});

window.Player = { loadBook, jumpToTrack, jumpToChapter, currentBookId };
