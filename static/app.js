// Main SPA controller
// Handles routing, API calls, and rendering library / book-detail / admin views.

import { fmt } from "./player.js";

const app = document.getElementById("app");

// ── Client-side logging ─────────────────────────────────────────────

window.clientLog = function clientLog(level, message, data) {
  const lvl = level || "info";
  console[lvl === "error" ? "error" : lvl === "warn" ? "warn" : "log"](
    "[client]", message, data ?? ""
  );
  fetch("/api/log", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ level: lvl, message, data }),
  }).catch(() => {});  // never let logging break the app
}

window.onerror = (msg, src, line, col, err) => {
  clientLog("error", String(msg), { src, line, col, stack: err?.stack });
};
window.onunhandledrejection = (e) => {
  clientLog("error", "Unhandled promise rejection", { reason: String(e.reason) });
};

// ── API client ─────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...opts });
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

// ── Session state ──────────────────────────────────────────────────

let _sessionPromise = null;

async function getSession() {
  if (!_sessionPromise) {
    _sessionPromise = api("/api/me").catch(() => ({ is_admin: false }));
  }
  return _sessionPromise;
}

// ── Router ─────────────────────────────────────────────────────────

function navigate(path, replace = false) {
  if (replace) history.replaceState(null, "", path);
  else history.pushState(null, "", path);
  route();
}
window.navigate = navigate;

window.addEventListener("popstate", route);

function route() {
  const path = location.pathname;
  clientLog("info", "navigate", { path });
  if (path === "/admin") {
    renderAdmin();
  } else {
    const m = path.match(/^\/book\/([a-f0-9]+)$/);
    if (m) renderBookDetail(m[1]);
    else renderLibrary();
  }
}

// ── Library state ──────────────────────────────────────────────────

let filterState = { search: "", author: "", series: "", tags: [], status: "" };
let metaCache = { authors: null, series: null, tags: null };
let savedLibraryScroll = 0;

// ── Tag autocomplete (shared, module-level) ─────────────────────────

let _tagDd = null;

function _ensureTagDd() {
  if (_tagDd) return _tagDd;
  _tagDd = document.createElement("div");
  _tagDd.className = "tag-dd hidden";
  document.body.appendChild(_tagDd);
  document.addEventListener("click", e => {
    if (!e.target.classList.contains("admin-input-tags")) _tagDd.classList.add("hidden");
  }, true);
  return _tagDd;
}

function showTagAutocomplete(input, allTags) {
  const dd = _ensureTagDd();
  const val = input.value;
  const lastComma = val.lastIndexOf(",");
  const partial = (lastComma >= 0 ? val.slice(lastComma + 1) : val).trimStart();
  if (!partial) { dd.classList.add("hidden"); return; }
  const used = val.split(",").map(t => t.trim().toLowerCase()).filter(Boolean);
  const matches = allTags.filter(t =>
    t.toLowerCase().startsWith(partial.toLowerCase()) && !used.includes(t.toLowerCase())
  ).slice(0, 8);
  if (!matches.length) { dd.classList.add("hidden"); return; }
  dd.innerHTML = matches.map(t => `<div class="tag-dd-item">${esc(t)}</div>`).join("");
  dd.classList.remove("hidden");
  const r = input.getBoundingClientRect();
  dd.style.cssText = `left:${r.left + scrollX}px;top:${r.bottom + scrollY + 2}px;min-width:${r.width}px`;
  dd.querySelectorAll(".tag-dd-item").forEach(item => {
    item.addEventListener("mousedown", e => {
      e.preventDefault();
      const prefix = lastComma >= 0 ? val.slice(0, lastComma + 1) + " " : "";
      input.value = prefix + item.textContent + ", ";
      dd.classList.add("hidden");
      input.focus();
    });
  });
}

// ── Helpers ────────────────────────────────────────────────────────

function fmtDuration(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function timeAgo(unixSecs) {
  const diff = Math.floor(Date.now() / 1000) - unixSecs;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function initials(title) {
  if (!title) return "?";
  return title.split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase() || "").join("");
}

function coverHtml(book, size = "card") {
  if (book.has_cover) {
    if (size === "detail") {
      return `<div class="detail-cover-wrap">
        <img src="/api/cover/${book.book_id}" alt="Cover" loading="lazy">
      </div>`;
    }
    return `<div class="book-cover-wrap">
      <img src="/api/cover/${book.book_id}" alt="Cover" loading="lazy">
    </div>`;
  }
  const text = initials(book.title);
  if (size === "detail") {
    return `<div class="detail-cover-wrap">
      <div class="detail-cover-placeholder">${text}</div>
    </div>`;
  }
  return `<div class="book-cover-wrap">
    <div class="book-cover-placeholder">${text}</div>
  </div>`;
}

function seriesBadge(book) {
  if (!book.series) return "";
  const num = book.number_in_series != null ? ` #${book.number_in_series}` : "";
  return `<span class="book-series-badge">${esc(book.series)}${num}</span>`;
}

function tagChips(tags, clickable = false) {
  if (!tags?.length) return "";
  return `<div class="tag-chips">${tags.map(t => `<span class="tag-chip${clickable ? " tag-chip-link" : ""}" ${clickable ? `data-tag="${esc(t)}"` : ""}>${esc(t)}</span>`).join("")}</div>`;
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function headerHtml(session) {
  const adminLink = session?.is_admin
    ? `<button class="btn" id="nav-admin">Admin</button>`
    : "";
  return `
    <div class="site-header">
      <div class="site-brand" id="nav-home">
        <img src="/icon-nav.svg" alt="" class="site-icon">
        <span class="site-name">bookthing</span>
      </div>
      ${adminLink}
      <form method="post" action="/auth/logout" style="margin:0">
        <button class="btn" type="submit">Sign out</button>
      </form>
    </div>`;
}

function wireHeaderEvents() {
  document.getElementById("nav-home")?.addEventListener("click", () => navigate("/"));
  document.getElementById("nav-admin")?.addEventListener("click", () => navigate("/admin"));
}

// ── Library view ───────────────────────────────────────────────────

async function renderLibrary() {
  app.innerHTML = `<div class="centered-msg"><span>Loading...</span></div>`;

  const [session] = await Promise.all([
    getSession(),
    metaCache.authors ? Promise.resolve() : Promise.all([
      api("/api/authors").catch(() => []).then(v => { metaCache.authors = v; }),
      api("/api/series").catch(() => []).then(v => { metaCache.series = v; }),
      api("/api/tags").catch(() => []).then(v => { metaCache.tags = v; }),
    ]),
  ]);

  await refreshLibraryView(session);
}

function calcPct(pos, book) {
  if (!pos) return 0;
  const durs = book.file_durations || [];
  const total = durs.reduce((a, v) => a + v, 0);
  if (total > 0) {
    const elapsed = durs.slice(0, pos.file_index).reduce((a, v) => a + v, 0) + pos.time_seconds;
    return Math.min(100, Math.max(1, Math.round((elapsed / total) * 100)));
  } else if (book.file_count > 0) {
    return Math.max(1, Math.round(((pos.file_index + 0.5) / book.file_count) * 100));
  }
  return 0;
}

function buildBookCards(books, positions) {
  return books.length
    ? books.map(b => {
        const pos = positions[b.book_id];
        const pct = calcPct(pos, b);
        const done = pct >= 99;
        const progressBar = pos
          ? `<div class="book-progress"><div class="book-progress-fill" style="width:${pct}%"></div></div>`
          : "";
        const doneCheck = done ? `<div class="book-done-check" title="Finished">✓</div>` : "";
        return `
        <div class="book-card" data-id="${b.book_id}">
          <div class="book-cover-container">
            ${coverHtml(b)}
            ${doneCheck}
          </div>
          <div class="book-info">
            <div class="book-title">${esc(b.title || "Untitled")}</div>
            <div class="book-author">${esc(b.author || "")}</div>
            ${seriesBadge(b)}
            ${tagChips(b.tags)}
          </div>
          ${progressBar}
        </div>`;
      }).join("")
    : `<div class="empty-state"><p>No books found.</p></div>`;
}

async function refreshLibraryView(session) {
  if (!session) session = await getSession();
  const params = new URLSearchParams();
  if (filterState.search) params.set("search", filterState.search);
  if (filterState.author) params.set("author", filterState.author);
  if (filterState.series) params.set("series", filterState.series);
  if (filterState.tags.length) params.set("tags", filterState.tags.join(","));

  let books, positions;
  try {
    [books, positions] = await Promise.all([
      api(`/api/books?${params}`),
      api("/api/positions").catch(() => ({})),
    ]);
  } catch (_) { return; }

  if (filterState.status === "listening") {
    books = books.filter(b => { const p = calcPct(positions[b.book_id], b); return p > 0 && p < 99; });
  } else if (filterState.status === "unlistened") {
    books = books.filter(b => !positions[b.book_id] || calcPct(positions[b.book_id], b) === 0);
  }

  // If the layout is already mounted, only update the book grid to preserve focus
  const grid = document.getElementById("book-grid");
  if (grid) {
    grid.innerHTML = buildBookCards(books, positions);
    return;
  }

  // Initial render — build the full layout and wire up event listeners
  const authorsOptions = (metaCache.authors || [])
    .map(a => `<option value="${esc(a)}" ${filterState.author === a ? "selected" : ""}>${esc(a)}</option>`)
    .join("");

  const seriesOptions = (metaCache.series || [])
    .map(s => `<option value="${esc(s)}" ${filterState.series === s ? "selected" : ""}>${esc(s)}</option>`)
    .join("");

  const tagChipsFilter = (metaCache.tags || [])
    .map(t => `<span class="tag-chip filter-tag-chip${filterState.tags.includes(t) ? " active" : ""}" data-tag="${esc(t)}">${esc(t)}</span>`)
    .join("");

  app.innerHTML = `
    ${headerHtml(session)}
    <button class="btn filter-toggle" id="filter-toggle-btn">☰ Filters</button>
    <div class="library-layout">
      <aside class="filter-sidebar" id="filter-sidebar">
        <h3>Filters</h3>
        <div class="filter-group">
          <label for="search-input">Search</label>
          <input type="text" id="search-input" placeholder="Title, author or series…" value="${esc(filterState.search)}">
        </div>
        <div class="filter-group">
          <label for="author-select">Author</label>
          <select id="author-select">
            <option value="">All authors</option>
            ${authorsOptions}
          </select>
        </div>
        <div class="filter-group">
          <label for="series-select">Series</label>
          <select id="series-select">
            <option value="">All series</option>
            ${seriesOptions}
          </select>
        </div>
        <div class="filter-group">
          <label>Tags</label>
          <div class="filter-tag-chips" id="filter-tag-chips">${tagChipsFilter}</div>
        </div>
        <div class="filter-group">
          <label>Status</label>
          <div class="filter-status-chips">
            <span class="status-chip${filterState.status === "" ? " active" : ""}" data-status="">All</span>
            <span class="status-chip${filterState.status === "listening" ? " active" : ""}" data-status="listening">Listening</span>
            <span class="status-chip${filterState.status === "unlistened" ? " active" : ""}" data-status="unlistened">Unlistened</span>
          </div>
        </div>
        <button class="btn btn-clear" id="clear-filters">Clear filters</button>
      </aside>
      <div class="book-grid" id="book-grid">${buildBookCards(books, positions)}</div>
    </div>`;

  // Restore scroll position when returning from a book detail page
  if (savedLibraryScroll > 0) {
    const y = savedLibraryScroll;
    savedLibraryScroll = 0;
    requestAnimationFrame(() => window.scrollTo(0, y));
  }

  wireHeaderEvents();
  document.getElementById("filter-toggle-btn").addEventListener("click", () => {
    document.getElementById("filter-sidebar").classList.toggle("open");
  });

  let searchDebounce;
  document.getElementById("search-input").addEventListener("input", e => {
    filterState.search = e.target.value;
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => refreshLibraryView(session), 300);
  });

  document.getElementById("author-select").addEventListener("change", e => {
    filterState.author = e.target.value;
    refreshLibraryView(session);
  });

  document.getElementById("series-select").addEventListener("change", e => {
    filterState.series = e.target.value;
    refreshLibraryView(session);
  });

  document.getElementById("filter-tag-chips").addEventListener("click", e => {
    const chip = e.target.closest(".filter-tag-chip");
    if (!chip) return;
    const tag = chip.dataset.tag;
    if (filterState.tags.includes(tag)) {
      filterState.tags = filterState.tags.filter(t => t !== tag);
    } else {
      filterState.tags = [...filterState.tags, tag];
    }
    chip.classList.toggle("active", filterState.tags.includes(tag));
    refreshLibraryView(session);
  });

  document.querySelector(".filter-status-chips").addEventListener("click", e => {
    const chip = e.target.closest(".status-chip");
    if (!chip) return;
    filterState.status = chip.dataset.status;
    document.querySelectorAll(".status-chip").forEach(c => c.classList.toggle("active", c.dataset.status === filterState.status));
    refreshLibraryView(session);
  });

  document.getElementById("clear-filters").addEventListener("click", () => {
    filterState = { search: "", author: "", series: "", tags: [], status: "" };
    document.getElementById("search-input").value = "";
    document.getElementById("author-select").value = "";
    document.getElementById("series-select").value = "";
    document.querySelectorAll(".filter-tag-chip").forEach(c => c.classList.remove("active"));
    document.querySelectorAll(".status-chip").forEach(c => c.classList.toggle("active", c.dataset.status === ""));
    refreshLibraryView(session);
  });

  document.getElementById("book-grid").addEventListener("click", e => {
    const card = e.target.closest(".book-card");
    if (card) {
      savedLibraryScroll = window.scrollY;
      navigate(`/book/${card.dataset.id}`);
    }
  });
}

// ── Book detail view ───────────────────────────────────────────────

async function renderBookDetail(bookId) {
  app.innerHTML = `<div class="centered-msg"><span>Loading...</span></div>`;
  let book, session, pos;
  try {
    [book, session, pos] = await Promise.all([
      api(`/api/books/${bookId}`),
      getSession(),
      api(`/api/position/${bookId}`).catch(() => null),
    ]);
  } catch (_) { return; }
  clientLog("info", "book detail", { book_id: bookId, title: book.title });

  const seriesLine = book.series
    ? `<div class="series detail-series-link" data-series="${esc(book.series)}">${esc(book.series)}${book.number_in_series != null ? ` #${book.number_in_series}` : ""}</div>`
    : "";

  const chapters = book.chapters || [];
  const hasChapters = chapters.length > 0;

  const chaptersHtml = hasChapters
    ? chapters.map((ch, i) => `
      <div class="chapter-item" data-start="${ch.start}">
        <span class="track-num">${i + 1}</span>
        <span class="track-name">${esc(ch.title)}</span>
      </div>`).join("")
    : "";

  const tracksHtml = !hasChapters
    ? (book.files || []).map((f, i) => `
      <div class="track-item" data-index="${i}">
        <span class="track-num">${i + 1}</span>
        <span class="track-name">${esc(f.name)}</span>
      </div>`).join("")
    : "";

  const trackSection = hasChapters
    ? `<div class="track-list-section">
        <h3>Chapters (${chapters.length})</h3>
        <div class="track-list">${chaptersHtml}</div>
      </div>`
    : book.file_count > 1
      ? `<div class="track-list-section">
          <h3>Tracks (${book.file_count})</h3>
          <div class="track-list">${tracksHtml}</div>
        </div>`
      : "";

  const adminEditBtn = session?.is_admin
    ? `<button class="btn" id="edit-meta-btn">Edit metadata</button>` : "";

  const descHtml = book.description
    ? `<div class="book-description">${book.description.split(/\n\s*\n/).map(p => `<p>${esc(p.trim())}</p>`).join("")}</div>`
    : "";

  const linksHtml = (book.links || []).length
    ? `<div class="book-links">${(book.links).map(l =>
        `<a class="book-link" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label || l.url)} &#8599;</a>`
      ).join("")}</div>`
    : "";

  const durationLine = book.total_seconds > 0
    ? `<div class="detail-duration">${fmtDuration(book.total_seconds)}</div>`
    : "";

  let progressLine = "";
  if (pos && (pos.file_index > 0 || pos.time_seconds > 0)) {
    const durs = book.file_durations || [];
    const total = durs.reduce((a, v) => a + v, 0);
    if (total > 0) {
      const elapsed = durs.slice(0, pos.file_index).reduce((a, v) => a + v, 0) + pos.time_seconds;
      const pct = Math.min(100, Math.round((elapsed / total) * 100));
      const remaining = Math.max(0, total - elapsed);
      const label = pct >= 99 ? "Complete" : `${pct}% · ${fmtDuration(remaining)} left`;
      progressLine = `<div class="detail-progress-line"><div class="detail-progress-bar"><div class="detail-progress-fill" style="width:${pct}%"></div></div><span class="detail-progress-label">${label}</span></div>`;
    }
  }

  app.innerHTML = `
    <div class="site-header">
      <div class="site-brand" id="nav-home">
        <img src="/icon-nav.svg" alt="" class="site-icon">
        <span class="site-name">bookthing</span>
      </div>
      <button class="btn" id="back-btn">&#8592; Library</button>
    </div>
    <div class="book-detail">
      <div class="book-detail-header">
        ${coverHtml(book, "detail")}
        <div class="detail-meta">
          <h1>${esc(book.title || "Untitled")}</h1>
          <div class="author">${(book.author || "").split(",").map(a => a.trim()).filter(Boolean).map(a => `<span class="detail-author-link" data-author="${esc(a)}">${esc(a)}</span>`).join(", ")}</div>
          ${seriesLine}
          ${tagChips(book.tags, true)}
          ${durationLine}
          ${progressLine}
          <div class="detail-actions">
            <button class="btn btn-accent" id="play-btn">&#9654; Play</button>
            <a class="btn" href="/api/download/${book.book_id}" download>&#8659; Download</a>
            ${adminEditBtn}
          </div>
        </div>
      </div>
      ${descHtml}
      ${linksHtml}
      ${trackSection}
    </div>`;

  document.getElementById("nav-home").addEventListener("click", () => navigate("/"));
  document.getElementById("back-btn").addEventListener("click", () => {
    if (history.length > 1) history.back();
    else navigate("/");
  });

  document.querySelector(".detail-meta .author")?.addEventListener("click", e => {
    const link = e.target.closest(".detail-author-link");
    if (!link) return;
    filterState = { search: "", author: link.dataset.author, series: "", tags: [] };
    navigate("/");
  });
  document.querySelector(".detail-series-link")?.addEventListener("click", () => {
    filterState = { search: "", author: "", series: book.series || "", tags: [] };
    navigate("/");
  });
  document.querySelectorAll(".tag-chip-link").forEach(el => {
    el.addEventListener("click", () => {
      filterState = { search: "", author: "", series: "", tags: [el.dataset.tag] };
      navigate("/");
    });
  });

  document.getElementById("play-btn").addEventListener("click", () => {
    clientLog("info", "play", { book_id: book.book_id, title: book.title });
    window.Player?.loadBook(book);
  });

  document.getElementById("edit-meta-btn")?.addEventListener("click", () => {
    navigate("/admin");
  });

  document.querySelectorAll(".track-item").forEach(el => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.index, 10);
      clientLog("info", "select track", { book_id: book.book_id, track: idx });
      if (window.Player?.currentBookId() === book.book_id) {
        window.Player.jumpToTrack(idx);
      } else {
        window.Player?.loadBook(book, idx);
      }
    });
  });

  document.querySelectorAll(".chapter-item").forEach(el => {
    el.addEventListener("click", () => {
      const start = parseFloat(el.dataset.start);
      clientLog("info", "select chapter", { book_id: book.book_id, start });
      if (window.Player?.currentBookId() === book.book_id) {
        window.Player.jumpToChapter(start);
      } else {
        window.Player?.loadBook(book, null, { startAtSeconds: start });
      }
    });
  });
}

// ── Admin view ─────────────────────────────────────────────────────

async function renderAdmin() {
  app.innerHTML = `<div class="centered-msg"><span>Loading…</span></div>`;

  let books, allAuthors, allSeries, allTags, activity, allowedEmails, users;
  try {
    [books, allAuthors, allSeries, allTags, activity, allowedEmails, users] = await Promise.all([
      api("/api/admin/books"),
      api("/api/authors").catch(() => []),
      api("/api/series").catch(() => []),
      api("/api/tags").catch(() => []),
      api("/api/admin/activity").catch(() => []),
      api("/api/admin/allowed-emails").catch(() => []),
      api("/api/admin/users").catch(() => []),
    ]);
  } catch {
    app.innerHTML = `<div class="centered-msg"><h2>Access denied</h2><p>Admin access required.</p></div>`;
    return;
  }

  // ── Folder groups ─────────────────────────────────────────────────
  const folderMap = {};
  for (const b of books) {
    const slash = (b.path || "").indexOf("/");
    const key = slash > 0 ? b.path.slice(0, slash) : "";
    if (!folderMap[key]) folderMap[key] = [];
    folderMap[key].push(b);
  }
  // Folders with >1 book, sorted alphabetically (root last)
  const bulkFolderOpts = Object.keys(folderMap)
    .filter(k => k !== "" && folderMap[k].length >= 1)
    .sort((a, b) => a.localeCompare(b))
    .map(k => `<option value="${esc(k)}">${esc(k)} — ${folderMap[k].length} book${folderMap[k].length !== 1 ? "s" : ""}</option>`)
    .join("");

  // ── Render helpers ────────────────────────────────────────────────
  let adminSearch = "";
  const activeMissingFilters = new Set();

  const MISSING_FILTERS = [
    { key: "no-author",      label: "No author",      test: b => !b.author },
    { key: "no-cover",       label: "No cover",       test: b => !b.has_cover },
    { key: "no-description", label: "No description", test: b => !b.description },
    { key: "no-series",      label: "No series",      test: b => !b.series },
    { key: "files-missing",  label: "Files missing",  test: b => !!b.missing },
    { key: "hidden",         label: "Hidden",         test: b => !!b.hidden },
  ];

  function getFiltered() {
    let result = books;
    if (adminSearch) {
      const s = adminSearch.toLowerCase();
      result = result.filter(b =>
        (b.title || "").toLowerCase().includes(s) ||
        (b.author || "").toLowerCase().includes(s) ||
        (b.path || "").toLowerCase().includes(s)
      );
    }
    if (activeMissingFilters.size > 0) {
      const active = MISSING_FILTERS.filter(f => activeMissingFilters.has(f.key));
      result = result.filter(b => active.some(f => f.test(b)));
    }
    return result;
  }

  function renderAdminTable(filteredBooks) {
    if (!filteredBooks.length) return `<div class="empty-state">No books match.</div>`;
    return filteredBooks.map(b => `
      <div class="admin-row ${b.missing ? "admin-row-missing" : ""} ${b.hidden ? "admin-row-hidden" : ""}" data-id="${b.book_id}">
        <div class="admin-cover-cell">
          <div class="admin-cover-thumb" id="thumb-${b.book_id}">
            ${b.has_cover
              ? `<img src="/api/cover/${b.book_id}" alt="">`
              : `<div class="admin-cover-placeholder">${esc(initials(b.title))}</div>`}
          </div>
          <label class="admin-upload-btn" title="Upload cover image">
            &#8593;<input type="file" accept="image/jpeg,image/png,image/webp"
              class="admin-cover-input" data-id="${b.book_id}" style="display:none">
          </label>
          ${b.has_cover
            ? `<button class="admin-delete-btn" data-id="${b.book_id}" title="Remove cover">&#215;</button>`
            : ""}
        </div>
        <div class="admin-fields">
          <div class="admin-path">${esc(b.path)}${b.missing ? ' <span class="missing-badge">missing</span>' : ""}</div>
          <div class="admin-field-row">
            <input class="admin-input" data-field="title" data-id="${b.book_id}"
              placeholder="Title" value="${esc(b.title || "")}">
            <input class="admin-input" data-field="author" data-id="${b.book_id}"
              placeholder="Author" value="${esc(b.author || "")}" list="dl-admin-authors">
          </div>
          <div class="admin-field-row">
            <input class="admin-input admin-input-series" data-field="series" data-id="${b.book_id}"
              placeholder="Series" value="${esc(b.series || "")}" list="dl-admin-series">
            <input class="admin-input admin-input-num" type="number" min="0" step="0.5"
              data-field="number_in_series" data-id="${b.book_id}"
              placeholder="#" value="${b.number_in_series ?? ""}">
            <input class="admin-input admin-input-tags" data-field="tags" data-id="${b.book_id}"
              placeholder="Tags (comma-separated)" value="${esc((b.tags || []).join(", "))}">
          </div>
          <div class="admin-field-row admin-field-desc">
            <textarea class="admin-input admin-input-desc" data-field="description" data-id="${b.book_id}"
              placeholder="Description…" rows="3">${esc(b.description || "")}</textarea>
            <button class="btn admin-fetch-btn" data-id="${b.book_id}" title="Fetch description from Google Books">Fetch ↓</button>
          </div>
          <div class="admin-fetch-results hidden" id="fetch-${b.book_id}"></div>
          <div class="admin-links-section" id="links-${b.book_id}">
            ${(b.links || []).map(l => `
              <div class="admin-link-row">
                <input class="admin-input admin-input-link-label" placeholder="Label" value="${esc(l.label || "")}">
                <input class="admin-input admin-input-link-url" placeholder="URL" value="${esc(l.url || "")}">
                <button class="btn admin-link-remove" type="button" title="Remove link">&#215;</button>
              </div>`).join("")}
          </div>
          <button class="btn admin-link-add" data-id="${b.book_id}" type="button">+ Link</button>
        </div>
        <div class="admin-actions-cell">
          <button class="btn admin-strip-btn" data-id="${b.book_id}" title="Replace underscores with spaces in all fields">Fix _</button>
          <button class="btn admin-hide-btn ${b.hidden ? "admin-hide-btn-on" : ""}" data-id="${b.book_id}" data-hidden="${b.hidden ? "1" : "0"}" title="${b.hidden ? "Unhide this book" : "Hide from library"}">${b.hidden ? "Unhide" : "Hide"}</button>
          <button class="btn admin-rescan-btn" data-id="${b.book_id}" title="Re-scan this book's folder to pick up new or changed files">Rescan</button>
          ${b.missing ? `<button class="btn admin-delete-btn" data-id="${b.book_id}" title="Remove this missing entry">Delete</button>` : ""}
          <button class="btn btn-accent admin-save-btn" data-id="${b.book_id}">Save</button>
          <span class="admin-status" id="status-${b.book_id}"></span>
        </div>
      </div>`).join("");
  }

  // ── Render page ───────────────────────────────────────────────────
  app.innerHTML = `
    <datalist id="dl-admin-authors">${allAuthors.map(a => `<option value="${esc(a)}">`).join("")}</datalist>
    <datalist id="dl-admin-series">${allSeries.map(s => `<option value="${esc(s)}">`).join("")}</datalist>

    <div class="site-header">
      <div class="site-brand" id="nav-home">
        <img src="/icon-nav.svg" alt="" class="site-icon">
        <span class="site-name">bookthing</span>
      </div>
      <span style="color:var(--accent);font-size:0.85rem;font-weight:600;">Admin</span>
      <button class="btn" id="nav-library">&#8592; Library</button>
    </div>

    ${activity.length ? `
    <div class="activity-section">
      <div class="activity-header" id="activity-toggle">
        <span>Recent activity</span>
        <span class="activity-caret">▾</span>
      </div>
      <div class="activity-body" id="activity-body">
        <table class="activity-table">
          <thead><tr><th>Who</th><th>Book</th><th>Position</th><th>When</th></tr></thead>
          <tbody>
            ${activity.map(a => {
              const ago = timeAgo(a.updated_at);
              const pos = a.time_seconds > 0
                ? `Track ${a.file_index + 1}, ${fmt(a.time_seconds)}`
                : `Track ${a.file_index + 1}`;
              return `<tr>
                <td class="act-label">${esc(a.email || "—")}</td>
                <td class="act-book"><span class="act-book-link" data-id="${a.book_id}">${esc(a.book_title)}</span></td>
                <td class="act-pos">${pos}</td>
                <td class="act-when">${ago}</td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>
    </div>` : ""}

    <div class="activity-section">
      <div class="activity-header" id="emails-toggle">
        <span>Allowed emails</span>
        <span class="activity-caret">▾</span>
      </div>
      <div class="activity-body hidden" id="emails-body">
        <div class="emails-add-row">
          <input type="email" id="new-email-input" placeholder="user@example.com">
          <label class="emails-admin-check">
            <input type="checkbox" id="new-email-admin"> Admin
          </label>
          <button class="btn btn-accent" id="add-email-btn">Add</button>
        </div>
        <table class="activity-table" id="emails-table">
          <thead><tr><th>Email</th><th>Admin</th><th></th></tr></thead>
          <tbody id="emails-tbody">
            ${allowedEmails.map(e => `
              <tr data-email="${esc(e.email)}">
                <td>${esc(e.email)}</td>
                <td>${e.is_admin ? "✓" : ""}</td>
                <td class="act-pos" style="display:flex;gap:0.4rem;align-items:center">
                  <button class="btn btn-sm send-link-btn" data-email="${esc(e.email)}">Send link</button>
                  <button class="btn btn-sm remove-email-btn" data-email="${esc(e.email)}">Remove</button>
                  <span class="send-link-status" data-email="${esc(e.email)}"></span>
                </td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>

    <div class="activity-section">
      <div class="activity-header" id="users-toggle">
        <span>Users</span>
        <span class="activity-caret">▾</span>
      </div>
      <div class="activity-body hidden" id="users-body">
        <table class="activity-table" id="users-table">
          <thead><tr><th>Email</th><th>Admin</th><th>Debug logging</th></tr></thead>
          <tbody id="users-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="admin-toolbar">
      <input type="text" id="admin-search" placeholder="Filter by title, author or path…" style="flex:1;max-width:400px">
      <button class="btn" id="bulk-toggle">Bulk Apply ▾</button>
      <button class="btn" id="scan-btn">Run Scan</button>
      <span class="admin-count" id="admin-count">${books.length} books</span>
    </div>
    <div class="scan-output hidden" id="scan-output"></div>
    <div class="admin-filter-chips">
      <span class="filter-chips-label">Show:</span>
      ${MISSING_FILTERS.map(f => `<button class="btn admin-chip" data-chip="${f.key}">${f.label}</button>`).join("")}
    </div>

    <div class="admin-bulk hidden" id="admin-bulk">
      <div class="admin-bulk-inner">
        <div class="admin-bulk-title">Apply to all books in a folder</div>
        <div class="admin-bulk-form">
          <div class="admin-bulk-field">
            <label>Folder</label>
            <select id="bulk-folder">
              <option value="">— select —</option>
              ${bulkFolderOpts}
            </select>
          </div>
          <div class="admin-bulk-field">
            <label>Author <span class="field-hint">blank = skip</span></label>
            <input type="text" id="bulk-author" placeholder="Author" list="dl-admin-authors">
          </div>
          <div class="admin-bulk-field">
            <label>Series <span class="field-hint">blank = skip</span></label>
            <input type="text" id="bulk-series" placeholder="Series" list="dl-admin-series">
          </div>
          <div class="admin-bulk-field">
            <label>Tags <span class="field-hint">blank = skip</span></label>
            <input type="text" id="bulk-tags" class="admin-input-tags" placeholder="tag1, tag2, …">
            <label class="admin-bulk-check">
              <input type="checkbox" id="bulk-tags-add"> Add to existing tags
            </label>
          </div>
        </div>
        <div class="admin-bulk-preview" id="bulk-preview"></div>
        <div class="admin-bulk-actions">
          <button class="btn btn-accent" id="bulk-apply" disabled>Apply</button>
          <span class="admin-status" id="bulk-status"></span>
        </div>
      </div>
    </div>

    <div class="admin-list" id="admin-list">
      ${renderAdminTable(books)}
    </div>`;

  // ── Nav ───────────────────────────────────────────────────────────
  document.getElementById("nav-home").addEventListener("click", () => navigate("/"));
  document.getElementById("nav-library").addEventListener("click", () => navigate("/"));

  // ── Activity section ──────────────────────────────────────────────
  document.getElementById("activity-toggle")?.addEventListener("click", () => {
    const body = document.getElementById("activity-body");
    const hidden = body.classList.toggle("hidden");
    document.querySelector("#activity-toggle .activity-caret").textContent = hidden ? "▾" : "▴";
  });
  document.querySelectorAll(".act-book-link").forEach(el => {
    el.addEventListener("click", () => navigate(`/book/${el.dataset.id}`));
  });

  // ── Allowed emails ─────────────────────────────────────────────────
  document.getElementById("emails-toggle").addEventListener("click", () => {
    const body = document.getElementById("emails-body");
    const hidden = body.classList.toggle("hidden");
    document.querySelector("#emails-toggle .activity-caret").textContent = hidden ? "▾" : "▴";
  });

  function renderEmailsTable(emails) {
    document.getElementById("emails-tbody").innerHTML = emails.map(e => `
      <tr data-email="${esc(e.email)}">
        <td>${esc(e.email)}</td>
        <td>${e.is_admin ? "✓" : ""}</td>
        <td style="display:flex;gap:0.4rem;align-items:center">
          <button class="btn btn-sm send-link-btn" data-email="${esc(e.email)}">Send link</button>
          <button class="btn btn-sm remove-email-btn" data-email="${esc(e.email)}">Remove</button>
          <span class="send-link-status" data-email="${esc(e.email)}"></span>
        </td>
      </tr>`).join("");
    document.querySelectorAll(".remove-email-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const email = btn.dataset.email;
        await api(`/api/admin/allowed-emails/${encodeURIComponent(email)}`, { method: "DELETE" });
        allowedEmails = allowedEmails.filter(e => e.email !== email);
        renderEmailsTable(allowedEmails);
      });
    });
    document.querySelectorAll(".send-link-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const email = btn.dataset.email;
        const status = document.querySelector(`.send-link-status[data-email="${email}"]`);
        btn.disabled = true;
        btn.textContent = "Sending…";
        status.textContent = "";
        try {
          await api(`/api/admin/send-login/${encodeURIComponent(email)}`, { method: "POST" });
          btn.textContent = "Send link";
          status.textContent = "✓ Sent";
          status.style.color = "var(--accent)";
          setTimeout(() => { status.textContent = ""; }, 4000);
        } catch {
          btn.textContent = "Send link";
          status.textContent = "✗ Failed";
          status.style.color = "#e06c75";
        }
        btn.disabled = false;
      });
    });
  }

  renderEmailsTable(allowedEmails);

  document.getElementById("add-email-btn").addEventListener("click", async () => {
    const input = document.getElementById("new-email-input");
    const btn = document.getElementById("add-email-btn");
    const email = input.value.trim().toLowerCase();
    const isAdmin = document.getElementById("new-email-admin").checked;
    if (!email || !email.includes("@")) return;
    btn.disabled = true;
    try {
      await api("/api/admin/allowed-emails", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, is_admin: isAdmin }),
      });
      allowedEmails = allowedEmails.filter(e => e.email !== email);
      allowedEmails.unshift({ email, is_admin: isAdmin ? 1 : 0 });
      renderEmailsTable(allowedEmails);
      input.value = "";
      document.getElementById("new-email-admin").checked = false;
    } catch {
      input.setCustomValidity("Failed to add email — please try again.");
      input.reportValidity();
      setTimeout(() => input.setCustomValidity(""), 3000);
    } finally {
      btn.disabled = false;
    }
  });

  // ── Users ──────────────────────────────────────────────────────────
  document.getElementById("users-toggle").addEventListener("click", () => {
    const body = document.getElementById("users-body");
    const hidden = body.classList.toggle("hidden");
    document.querySelector("#users-toggle .activity-caret").textContent = hidden ? "▾" : "▴";
  });

  function renderUsersTable(userList) {
    document.getElementById("users-tbody").innerHTML = userList.map(u => `
      <tr data-email="${esc(u.email)}">
        <td>${esc(u.email)}</td>
        <td>${u.is_admin ? "✓" : ""}</td>
        <td>
          <label class="debug-toggle">
            <input type="checkbox" class="debug-logging-chk" data-email="${esc(u.email)}"
              ${u.debug_logging ? "checked" : ""}>
            <span class="debug-toggle-label">${u.debug_logging ? "On" : "Off"}</span>
          </label>
        </td>
      </tr>`).join("");
    document.querySelectorAll(".debug-logging-chk").forEach(chk => {
      chk.addEventListener("change", async () => {
        const email = chk.dataset.email;
        const enabled = chk.checked;
        chk.disabled = true;
        try {
          await api(`/api/admin/users/${encodeURIComponent(email)}/debug-logging`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled }),
          });
          const u = users.find(u => u.email === email);
          if (u) u.debug_logging = enabled ? 1 : 0;
          chk.nextElementSibling.textContent = enabled ? "On" : "Off";
        } catch {
          chk.checked = !enabled;
        } finally {
          chk.disabled = false;
        }
      });
    });
  }

  renderUsersTable(users);

  // ── Scan ─────────────────────────────────────────────────────────
  document.getElementById("scan-btn").addEventListener("click", async () => {
    const btn = document.getElementById("scan-btn");
    const out = document.getElementById("scan-output");
    btn.disabled = true;
    btn.textContent = "Scanning…";
    out.classList.remove("hidden");
    out.textContent = "Running scan…";
    try {
      const res = await fetch("/api/admin/scan", { method: "POST", credentials: "same-origin" });
      const data = await res.json();
      out.textContent = data.output || (data.ok ? "Scan complete." : "Scan failed.");
      out.className = "scan-output" + (data.ok ? "" : " scan-output-error");
    } catch (e) {
      clientLog("error", "Scan request failed", { message: e.message });
      out.textContent = "Scan request failed: " + e.message;
      out.className = "scan-output scan-output-error";
    }
    btn.disabled = false;
    btn.textContent = "Run Scan";
  });

  // ── Bulk toggle ───────────────────────────────────────────────────
  document.getElementById("bulk-toggle").addEventListener("click", () => {
    const bulk = document.getElementById("admin-bulk");
    const open = bulk.classList.toggle("hidden") === false;
    document.getElementById("bulk-toggle").textContent = open ? "Bulk Apply ▴" : "Bulk Apply ▾";
  });

  // ── Bulk folder preview ───────────────────────────────────────────
  function updateBulkPreview() {
    const key = document.getElementById("bulk-folder").value;
    const preview = document.getElementById("bulk-preview");
    const applyBtn = document.getElementById("bulk-apply");
    if (!key) { preview.innerHTML = ""; applyBtn.disabled = true; return; }
    const affected = folderMap[key] || [];
    applyBtn.disabled = !affected.length;
    const items = affected.slice(0, 6).map(b => `<li>${esc(b.title || b.path)}</li>`).join("");
    const more = affected.length > 6 ? `<li class="preview-more">…and ${affected.length - 6} more</li>` : "";
    preview.innerHTML = `
      <div class="preview-count">${affected.length} book${affected.length !== 1 ? "s" : ""} will be updated</div>
      <ul class="preview-list">${items}${more}</ul>`;
  }
  document.getElementById("bulk-folder").addEventListener("change", updateBulkPreview);

  // ── Bulk apply ────────────────────────────────────────────────────
  document.getElementById("bulk-apply").addEventListener("click", async () => {
    const key = document.getElementById("bulk-folder").value;
    const affected = folderMap[key] || [];
    if (!affected.length) return;
    const author  = document.getElementById("bulk-author").value.trim();
    const series  = document.getElementById("bulk-series").value.trim();
    const tagsRaw = document.getElementById("bulk-tags").value.trim();
    const tagsAdd = document.getElementById("bulk-tags-add").checked;
    const fields  = {};
    if (author)  fields.author = author;
    if (series)  fields.series = series;
    if (tagsRaw) fields.tags   = tagsRaw;
    if (!Object.keys(fields).length) {
      document.getElementById("bulk-status").textContent = "Nothing to apply — fill in at least one field";
      return;
    }
    const btn = document.getElementById("bulk-apply");
    const status = document.getElementById("bulk-status");
    btn.disabled = true;
    status.textContent = "Applying…";
    status.className = "admin-status";
    try {
      const res = await api("/api/admin/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ book_ids: affected.map(b => b.book_id), fields, tags_mode: tagsAdd ? "add" : "replace" }),
      });
      // Update local book cache
      const parsedTags = tagsRaw ? tagsRaw.split(",").map(t => t.trim()).filter(Boolean) : null;
      for (const b of affected) {
        if (author) b.author = author;
        if (series) b.series = series;
        if (parsedTags !== null) {
          if (tagsAdd) {
            const combined = new Set([...(b.tags || []), ...parsedTags]);
            b.tags = [...combined];
          } else {
            b.tags = parsedTags;
          }
        }
      }
      // Re-render to show changes
      document.getElementById("admin-list").innerHTML = renderAdminTable(getFiltered());
      wireAdminRows();
      // Update datalists
      if (author && !allAuthors.includes(author)) {
        allAuthors.push(author);
        document.getElementById("dl-admin-authors").innerHTML += `<option value="${esc(author)}">`;
      }
      if (series && !allSeries.includes(series)) {
        allSeries.push(series);
        document.getElementById("dl-admin-series").innerHTML += `<option value="${esc(series)}">`;
      }
      metaCache = { authors: null, series: null, tags: null };
      status.textContent = `Updated ${res.updated} book${res.updated !== 1 ? "s" : ""}`;
      status.className = "admin-status admin-status-ok";
    } catch {
      status.textContent = "Error";
      status.className = "admin-status admin-status-err";
    } finally {
      btn.disabled = false;
      setTimeout(() => { status.textContent = ""; }, 4000);
    }
  });

  // Wire bulk tags autocomplete
  const bulkTagsInput = document.getElementById("bulk-tags");
  bulkTagsInput.addEventListener("input",  () => showTagAutocomplete(bulkTagsInput, allTags));
  bulkTagsInput.addEventListener("focus",  () => showTagAutocomplete(bulkTagsInput, allTags));

  // ── Missing-metadata filter chips ─────────────────────────────────
  function refreshAdminList() {
    const filtered = getFiltered();
    document.getElementById("admin-list").innerHTML = renderAdminTable(filtered);
    document.getElementById("admin-count").textContent =
      filtered.length === books.length ? `${books.length} books` : `${filtered.length} / ${books.length} books`;
    wireAdminRows();
  }

  document.querySelectorAll(".admin-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const key = chip.dataset.chip;
      if (activeMissingFilters.has(key)) {
        activeMissingFilters.delete(key);
        chip.classList.remove("btn-accent");
      } else {
        activeMissingFilters.add(key);
        chip.classList.add("btn-accent");
      }
      refreshAdminList();
    });
  });

  // ── Search ────────────────────────────────────────────────────────
  let searchTimer;
  document.getElementById("admin-search").addEventListener("input", e => {
    adminSearch = e.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(refreshAdminList, 200);
  });

  // ── Wire rows ─────────────────────────────────────────────────────
  wireAdminRows();

  function markDirty(id) {
    document.querySelector(`.admin-row[data-id="${id}"]`)?.classList.add("admin-row-dirty");
  }

  function wireAdminRows() {
    // Dirty-state tracking — mark row when any field changes
    document.querySelectorAll(".admin-row[data-id]").forEach(row => {
      const id = row.dataset.id;
      row.querySelectorAll("input[data-field], textarea[data-field]").forEach(el => {
        el.addEventListener("input", () => markDirty(id));
        el.addEventListener("change", () => markDirty(id));
      });
    });

    // Tag autocomplete on each row
    document.querySelectorAll(".admin-input-tags").forEach(input => {
      if (input.id === "bulk-tags") return; // already wired above
      input.addEventListener("input", () => showTagAutocomplete(input, allTags));
      input.addEventListener("focus", () => showTagAutocomplete(input, allTags));
    });

    // Add link button
    document.querySelectorAll(".admin-link-add").forEach(btn => {
      btn.addEventListener("click", () => {
        const section = document.getElementById(`links-${btn.dataset.id}`);
        const row = document.createElement("div");
        row.className = "admin-link-row";
        row.innerHTML = `
          <input class="admin-input admin-input-link-label" placeholder="Label">
          <input class="admin-input admin-input-link-url" placeholder="URL">
          <button class="btn admin-link-remove" type="button" title="Remove link">&#215;</button>`;
        section.appendChild(row);
        row.querySelector(".admin-input-link-url").focus();
        markDirty(btn.dataset.id);
      });
    });

    // Remove link button (delegated on each links section)
    document.querySelectorAll(".admin-links-section").forEach(section => {
      section.addEventListener("click", e => {
        const removeBtn = e.target.closest(".admin-link-remove");
        if (!removeBtn) return;
        const row = removeBtn.closest(".admin-link-row");
        const bookId = section.id.replace("links-", "");
        row.remove();
        markDirty(bookId);
      });
    });

    // Rescan button
    document.querySelectorAll(".admin-rescan-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const status = document.getElementById(`status-${id}`);
        btn.disabled = true;
        btn.textContent = "Scanning…";
        status.textContent = "";
        status.className = "admin-status";
        try {
          const data = await api(`/api/admin/books/${id}/rescan`, { method: "POST" });
          if (data.ok) {
            // Reload admin page to reflect updated files/cover
            navigate("/admin", true);
          } else {
            status.textContent = data.output?.trim() || "Rescan failed.";
            status.className = "admin-status admin-status-err";
            btn.disabled = false;
            btn.textContent = "Rescan";
          }
        } catch (e) {
          clientLog("error", "Rescan failed", { id, message: e.message });
          status.textContent = "Rescan failed.";
          status.className = "admin-status admin-status-err";
          btn.disabled = false;
          btn.textContent = "Rescan";
        }
      });
    });

    // Strip underscores button
    document.querySelectorAll(".admin-strip-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.id;
        const row = document.querySelector(`.admin-row[data-id="${id}"]`);
        ["title", "author", "series"].forEach(field => {
          const inp = row.querySelector(`[data-field="${field}"]`);
          if (inp) inp.value = inp.value.replace(/_/g, " ").replace(/  +/g, " ").trim();
        });
        const tagsInp = row.querySelector(`[data-field="tags"]`);
        if (tagsInp) {
          tagsInp.value = tagsInp.value
            .split(",")
            .map(t => t.replace(/_/g, " ").replace(/  +/g, " ").trim())
            .filter(Boolean)
            .join(", ");
        }
        markDirty(id);
      });
    });

    // Save buttons
    document.querySelectorAll(".admin-save-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const row = document.querySelector(`.admin-row[data-id="${id}"]`);
        const get = f => row.querySelector(`[data-field="${f}"][data-id="${id}"]`)?.value ?? "";
        const tagsVal = get("tags");
        const links = [...row.querySelectorAll(`#links-${id} .admin-link-row`)].map(r => ({
          label: r.querySelector(".admin-input-link-label").value.trim(),
          url: r.querySelector(".admin-input-link-url").value.trim(),
        })).filter(l => l.url);
        const payload = {
          title: get("title"),
          author: get("author"),
          series: get("series"),
          number_in_series: get("number_in_series") || null,
          tags: tagsVal,
          description: get("description"),
          links,
        };
        const status = document.getElementById(`status-${id}`);
        btn.disabled = true;
        status.textContent = "Saving…";
        status.className = "admin-status";
        try {
          await api(`/api/admin/books/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const book = books.find(b => b.book_id === id);
          if (book) {
            book.title  = payload.title;
            book.author = payload.author;
            book.series = payload.series;
            book.number_in_series = payload.number_in_series ? parseFloat(payload.number_in_series) : null;
            book.tags   = tagsVal.split(",").map(t => t.trim()).filter(Boolean);
          }
          // Update datalists with any new values
          if (payload.author && !allAuthors.includes(payload.author)) {
            allAuthors.push(payload.author);
            document.getElementById("dl-admin-authors").innerHTML += `<option value="${esc(payload.author)}">`;
          }
          if (payload.series && !allSeries.includes(payload.series)) {
            allSeries.push(payload.series);
            document.getElementById("dl-admin-series").innerHTML += `<option value="${esc(payload.series)}">`;
          }
          for (const t of tagsVal.split(",").map(x => x.trim()).filter(Boolean)) {
            if (!allTags.includes(t)) allTags.push(t);
          }
          metaCache = { authors: null, series: null, tags: null };
          // Clear dirty state on success
          row.classList.remove("admin-row-dirty");
          status.textContent = "✓ Saved";
          status.className = "admin-status admin-status-ok";
        } catch {
          status.textContent = "Error";
          status.className = "admin-status admin-status-err";
        } finally {
          btn.disabled = false;
          setTimeout(() => { status.textContent = ""; }, 3000);
        }
      });
    });

    // Delete missing entries
    document.querySelectorAll(".admin-delete-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const row = document.querySelector(`.admin-row[data-id="${id}"]`);
        const title = books.find(b => b.book_id === id)?.title || id;
        if (!window.confirm(`Remove "${title}" from the library?\n\nThis only removes the metadata entry — no files are deleted.`)) return;
        btn.disabled = true;
        const status = document.getElementById(`status-${id}`);
        status.textContent = "Deleting…";
        status.className = "admin-status";
        try {
          await api(`/api/admin/books/${id}`, { method: "DELETE" });
          // Remove from local array and DOM
          const idx = books.findIndex(b => b.book_id === id);
          if (idx !== -1) books.splice(idx, 1);
          row.remove();
          const countEl = document.getElementById("admin-count");
          const filtered = getFiltered();
          countEl.textContent = filtered.length === books.length
            ? `${books.length} books`
            : `${filtered.length} / ${books.length} books`;
        } catch {
          status.textContent = "Error";
          status.className = "admin-status admin-status-err";
          btn.disabled = false;
          setTimeout(() => { status.textContent = ""; }, 3000);
        }
      });
    });

    // Hide / unhide toggle
    document.querySelectorAll(".admin-hide-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const nowHidden = btn.dataset.hidden === "1";
        const newHidden = !nowHidden;
        btn.disabled = true;
        const status = document.getElementById(`status-${id}`);
        status.textContent = newHidden ? "Hiding…" : "Unhiding…";
        status.className = "admin-status";
        try {
          await api(`/api/admin/books/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hidden: newHidden }),
          });
          // Update local book object
          const book = books.find(b => b.book_id === id);
          if (book) book.hidden = newHidden;
          // Update button state
          btn.dataset.hidden = newHidden ? "1" : "0";
          btn.textContent = newHidden ? "Unhide" : "Hide";
          btn.title = newHidden ? "Unhide this book" : "Hide from library";
          btn.classList.toggle("admin-hide-btn-on", newHidden);
          // Update row class
          const row = document.querySelector(`.admin-row[data-id="${id}"]`);
          row?.classList.toggle("admin-row-hidden", newHidden);
          status.textContent = newHidden ? "Hidden" : "Visible";
          status.className = "admin-status admin-status-ok";
        } catch {
          status.textContent = "Error";
          status.className = "admin-status admin-status-err";
        } finally {
          btn.disabled = false;
          setTimeout(() => { status.textContent = ""; }, 2500);
        }
      });
    });

    // Fetch description from Google Books
    document.querySelectorAll(".admin-fetch-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const resultsEl = document.getElementById(`fetch-${id}`);
        const textarea = document.querySelector(`textarea[data-field="description"][data-id="${id}"]`);
        btn.disabled = true;
        btn.textContent = "…";
        resultsEl.innerHTML = "";
        resultsEl.classList.add("hidden");
        try {
          const data = await api(`/api/admin/books/${id}/fetch-description`);
          if (!data.candidates?.length) {
            resultsEl.innerHTML = `<div class="fetch-none">No descriptions found on Google Books.</div>`;
            resultsEl.classList.remove("hidden");
            return;
          }
          resultsEl.innerHTML = data.candidates.map((c, i) => `
            <div class="fetch-candidate" data-index="${i}">
              <div class="fetch-candidate-title">${esc(c.title)}${c.authors?.length ? ` <span class="fetch-candidate-authors">— ${esc(c.authors.join(", "))}</span>` : ""}</div>
              <div class="fetch-candidate-desc">${esc(c.description.slice(0, 200))}${c.description.length > 200 ? "…" : ""}</div>
            </div>`).join("");
          resultsEl.classList.remove("hidden");
          // Store full descriptions for click handler
          const candidates = data.candidates;
          resultsEl.querySelectorAll(".fetch-candidate").forEach(card => {
            card.addEventListener("click", () => {
              const c = candidates[parseInt(card.dataset.index, 10)];
              textarea.value = c.description;
              resultsEl.innerHTML = "";
              resultsEl.classList.add("hidden");
            });
          });
        } catch {
          resultsEl.innerHTML = `<div class="fetch-none">Error contacting Google Books.</div>`;
          resultsEl.classList.remove("hidden");
        } finally {
          btn.disabled = false;
          btn.textContent = "Fetch ↓";
        }
      });
    });

    // Cover upload
    document.querySelectorAll(".admin-cover-input").forEach(input => {
      input.addEventListener("change", async () => {
        const id = input.dataset.id;
        const file = input.files[0];
        if (!file) return;
        const status = document.getElementById(`status-${id}`);
        status.textContent = "Uploading…";
        status.className = "admin-status";
        const form = new FormData();
        form.append("file", file);
        try {
          const res = await fetch(`/api/admin/books/${id}/cover`, {
            method: "POST", credentials: "same-origin", body: form,
          });
          if (!res.ok) throw new Error(await res.text());
          document.getElementById(`thumb-${id}`).innerHTML =
            `<img src="/api/cover/${id}?t=${Date.now()}" alt="">`;
          const book = books.find(b => b.book_id === id);
          if (book) book.has_cover = true;
          status.textContent = "Uploaded";
          status.className = "admin-status admin-status-ok";
        } catch {
          status.textContent = "Upload failed";
          status.className = "admin-status admin-status-err";
        } finally {
          setTimeout(() => { status.textContent = ""; }, 3000);
          input.value = "";
        }
      });
    });

    // Cover delete
    document.querySelectorAll(".admin-delete-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const status = document.getElementById(`status-${id}`);
        status.textContent = "Removing…";
        status.className = "admin-status";
        try {
          const res = await fetch(`/api/admin/books/${id}/cover`, {
            method: "DELETE", credentials: "same-origin",
          });
          if (!res.ok) throw new Error(await res.text());
          const initials_text = esc(initials((books.find(b => b.book_id === id) || {}).title || ""));
          document.getElementById(`thumb-${id}`).innerHTML =
            `<div class="admin-cover-placeholder">${initials_text}</div>`;
          const book = books.find(b => b.book_id === id);
          if (book) book.has_cover = false;
          btn.remove();
          status.textContent = "Removed";
          status.className = "admin-status admin-status-ok";
        } catch {
          status.textContent = "Remove failed";
          status.className = "admin-status admin-status-err";
        } finally {
          setTimeout(() => { status.textContent = ""; }, 3000);
        }
      });
    });
  }
}

// ── Auth error ─────────────────────────────────────────────────────

function redirectToLogin() {
  window.location.href = "/login";
}

// ── Boot ───────────────────────────────────────────────────────────

async function restorePlayer() {
  let bookId;
  try { bookId = localStorage.getItem("bookthing.lastBook"); } catch (_) {}
  if (!bookId) return;
  try {
    const book = await api(`/api/books/${bookId}`);
    // Restore player bar in paused state — user presses play to resume
    window.Player?.loadBook(book, null, { paused: true });
  } catch (_) {
    // Book no longer exists or session expired — clear stale entry
    try { localStorage.removeItem("bookthing.lastBook"); } catch (__) {}
  }
}

route();
restorePlayer();
