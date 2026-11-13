// Progressive enhancements. Every page still works without JavaScript:
// links and forms are real links and forms; this adds overlays, search-as-you-type,
// the theme switcher and keyboard shortcuts.
(function () {
  "use strict";

  var root = document.documentElement;

  // ---- Theme ---------------------------------------------------------------
  function effectiveTheme() {
    var chosen = root.getAttribute("data-theme");
    if (chosen) return chosen;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function setTheme(choice) {
    if (choice === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", choice);
    try {
      if (choice === "system") localStorage.removeItem("theme");
      else localStorage.setItem("theme", choice);
    } catch (e) {
      /* storage blocked: the choice lasts for this page only */
    }
    markTheme();
  }
  function markTheme() {
    var chosen = root.getAttribute("data-theme") || "system";
    document.querySelectorAll("[data-theme-choice]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-theme-choice") === chosen));
    });
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(effectiveTheme() === "dark"));
      b.setAttribute("title", effectiveTheme() === "dark" ? "Switch to light mode" : "Switch to dark mode");
    });
  }

  // ---- Dialogs (menu overlay, help) -----------------------------------------
  function openDialog(id) {
    var dialog = document.getElementById(id);
    if (dialog && !dialog.open) dialog.showModal();
  }

  // ---- Popovers (<details data-popover>) ------------------------------------
  function closePopovers(except) {
    document.querySelectorAll("details[data-popover][open]").forEach(function (d) {
      if (d !== except) d.removeAttribute("open");
    });
  }

  // ---- Clicks ----------------------------------------------------------------
  document.addEventListener("click", function (event) {
    var t = event.target;

    var choice = t.closest("[data-theme-choice]");
    if (choice) return setTheme(choice.getAttribute("data-theme-choice"));

    if (t.closest("[data-theme-toggle]")) return setTheme(effectiveTheme() === "dark" ? "light" : "dark");

    // Audit packet: the browser's print dialog also offers "Save as PDF".
    if (t.closest("[data-print]")) return window.print();

    var opener = t.closest("[data-open-dialog]");
    if (opener) {
      closePopovers();
      hideResults();
      return openDialog(opener.getAttribute("data-open-dialog"));
    }

    var closer = t.closest("[data-close-dialog]");
    if (closer) return closer.closest("dialog").close();

    // Click on a dialog's backdrop closes it.
    if (t.tagName === "DIALOG" && t.open) {
      var box = t.getBoundingClientRect();
      var inside = event.clientX >= box.left && event.clientX <= box.right &&
                   event.clientY >= box.top && event.clientY <= box.bottom;
      if (!inside) t.close();
    }

    closePopovers(t.closest("details[data-popover]"));
    if (!t.closest("[data-search-form], [data-search-panel]")) hideResults();

    // Disclosure buttons: <button data-toggle-target="id" aria-expanded>
    var button = t.closest("[data-toggle-target]");
    if (button) {
      var target = document.getElementById(button.getAttribute("data-toggle-target"));
      if (!target) return;
      var expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      target.classList.toggle("hidden", expanded);
    }
  });

  // ---- Recents: this browser only, per user and per carrier --------------------
  // Keyed by carrier so a driver viewed in one carrier never appears in another.
  var body = document.body;
  var recentKey = body.dataset.user ? "recents:" + body.dataset.user + ":" + body.dataset.tenant : null;
  var MAX_RECENTS = 6;

  function loadRecents() {
    if (!recentKey) return [];
    try {
      var list = JSON.parse(localStorage.getItem(recentKey) || "[]");
      return Array.isArray(list) ? list : [];
    } catch (e) {
      return [];
    }
  }
  function saveRecent() {
    if (!recentKey || !body.dataset.recentTitle) return;
    var here = { title: body.dataset.recentTitle, kind: body.dataset.recentKind || "Page", url: location.pathname };
    var list = loadRecents().filter(function (r) { return r.url !== here.url; });
    list.unshift(here);
    try {
      localStorage.setItem(recentKey, JSON.stringify(list.slice(0, MAX_RECENTS)));
    } catch (e) {
      /* storage full or blocked: recents are a convenience only */
    }
  }
  function clearRecents() {
    try {
      var prefix = "recents:" + body.dataset.user + ":";
      Object.keys(localStorage).forEach(function (k) {
        if (k.indexOf(prefix) === 0) localStorage.removeItem(k);
      });
    } catch (e) {
      /* nothing stored */
    }
  }
  function isSafePath(url) {
    return typeof url === "string" && url.charAt(0) === "/" && url.charAt(1) !== "/";
  }

  // ---- Search bar (bottom) ---------------------------------------------------
  var input = document.getElementById("global-search");
  var panel = document.querySelector("[data-search-panel]");
  var pending = null;
  var lastQuery = "";

  function hideResults() {
    if (!panel) return;
    panel.hidden = true;
    if (input) input.setAttribute("aria-expanded", "false");
  }
  function showResults() {
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function renderRecents() {
    var section = panel.querySelector("[data-recents-section]");
    var list = panel.querySelector("[data-recents-list]");
    list.replaceChildren();
    var items = loadRecents().filter(function (r) {
      return isSafePath(r.url) && r.url !== location.pathname;
    });
    items.forEach(function (r) {
      list.append(resultRow({ url: r.url, title: r.title, detail: "", kind: r.kind }));
    });
    section.hidden = items.length === 0;
  }

  // ---- Home: "Pick up where you left off" ------------------------------------
  // Same per-user, per-carrier store as the search bar's recents.
  function renderLauncherRecents() {
    var section = document.querySelector("[data-launcher-recents]");
    if (!section) return;
    var list = section.querySelector("[data-launcher-recents-list]");
    var items = loadRecents().filter(function (r) { return isSafePath(r.url) && r.url !== location.pathname; }).slice(0, 4);
    items.forEach(function (r) {
      var li = resultRow({ url: r.url, title: r.title, detail: "", kind: r.kind });
      li.firstChild.classList.add("glass");
      list.append(li);
    });
    section.hidden = items.length === 0;
  }

  function resultRow(r) {
    // Built with textContent: record names never become HTML.
    var li = document.createElement("li");
    var a = document.createElement("a");
    a.href = r.url;
    a.className = "transition-soft flex items-center justify-between gap-3 rounded-2xl px-3 py-2 hover:bg-tint/5 focus:bg-tint/5";
    var left = document.createElement("span");
    left.className = "min-w-0";
    var title = document.createElement("span");
    title.className = "block truncate text-sm font-semibold";
    title.textContent = r.title;
    left.append(title);
    if (r.detail) {
      var detail = document.createElement("span");
      detail.className = "block truncate text-xs text-muted";
      detail.textContent = r.detail;
      left.append(detail);
    }
    var kind = document.createElement("span");
    kind.className = "shrink-0 rounded-full bg-tint/[0.06] px-2 py-0.5 text-[11px] font-medium text-muted";
    kind.textContent = r.kind;
    a.append(left, kind);
    li.append(a);
    return li;
  }

  function renderRecords(results) {
    var section = panel.querySelector("[data-records-section]");
    var list = panel.querySelector("[data-records-list]");
    list.replaceChildren();
    results.forEach(function (r) { list.append(resultRow(r)); });
    section.hidden = results.length === 0;
    updateEmpty();
  }

  function updateEmpty() {
    var anyPage = panel.querySelector("[data-page-result]:not([hidden])");
    panel.querySelector("[data-pages-section]").hidden = !anyPage;
    var anyRecord = !panel.querySelector("[data-records-section]").hidden;
    var anyRecent = !panel.querySelector("[data-recents-section]").hidden;
    panel.querySelector("[data-no-results]").hidden = Boolean(anyPage || anyRecord || anyRecent);
  }

  // Score a page for the typed words: label prefix beats word prefix beats keyword.
  function pageScore(li, words) {
    var label = li.getAttribute("data-label");
    var haystack = li.getAttribute("data-search-text").split(/\s+/);
    var score = 0;
    for (var i = 0; i < words.length; i++) {
      var w = words[i];
      if (label.indexOf(w) === 0) score += 3;
      else if (label.split(" ").some(function (part) { return part.indexOf(w) === 0; })) score += 2;
      else if (haystack.some(function (part) { return part.indexOf(w) === 0; })) score += 1;
      else return 0; // every word must match something
    }
    return score;
  }

  function rankPages(q) {
    var items = Array.prototype.slice.call(panel.querySelectorAll("[data-page-result]"));
    var list = items.length ? items[0].parentNode : null;
    var words = q.split(/\s+/).filter(Boolean);
    items.forEach(function (li, index) {
      li._order = li._order === undefined ? index : li._order; // original menu order
      li._score = words.length ? pageScore(li, words) : 1;
      li.hidden = li._score === 0;
    });
    items
      .sort(function (a, b) { return b._score - a._score || a._order - b._order; })
      .forEach(function (li) { list.append(li); });
    panel.querySelector("[data-pages-heading]").textContent = words.length ? "Suggestions" : "Go to";
  }

  function runSearch() {
    var q = input.value.trim().toLowerCase();
    rankPages(q);
    if (q === "") renderRecents();
    else panel.querySelector("[data-recents-section]").hidden = true;
    showResults();
    updateEmpty();
    if (q.length < 2 || input.getAttribute("data-has-tenant") !== "true") {
      renderRecords([]);
      return;
    }
    if (q === lastQuery) return;
    lastQuery = q;
    clearTimeout(pending);
    pending = setTimeout(function () {
      fetch(input.getAttribute("data-search-url") + "?q=" + encodeURIComponent(q), {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (r) { return r.ok ? r.json() : { results: [] }; })
        .then(function (data) { if (input.value.trim().toLowerCase() === q) renderRecords(data.results || []); })
        .catch(function () { renderRecords([]); });
    }, 160);
  }

  if (input && panel) {
    input.addEventListener("input", runSearch);
    input.addEventListener("focus", runSearch);
    input.closest("form").addEventListener("submit", function (event) {
      event.preventDefault();
      var first = panel.querySelector("[data-page-result]:not([hidden]) a, [data-records-list] a");
      if (first) window.location.assign(first.href);
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        var first = panel.querySelector("a:not([hidden] a)");
        if (first) { event.preventDefault(); first.focus(); }
      }
    });
    panel.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      var links = Array.prototype.filter.call(panel.querySelectorAll("a"), function (a) {
        return !a.closest("[hidden]");
      });
      var i = links.indexOf(document.activeElement);
      event.preventDefault();
      if (event.key === "ArrowDown" && i < links.length - 1) links[i + 1].focus();
      if (event.key === "ArrowUp") (i > 0 ? links[i - 1] : input).focus();
    });
  }

  // ---- Keyboard shortcuts -------------------------------------------------------
  document.addEventListener("keydown", function (event) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if ((event.key === "k" && (event.metaKey || event.ctrlKey)) || (event.key === "/" && !typing)) {
      if (input) {
        event.preventDefault();
        document.querySelectorAll("dialog[open]").forEach(function (d) { d.close(); });
        input.focus();
        input.select();
      }
    }
    if (event.key === "Escape") {
      if (panel && !panel.hidden) { hideResults(); if (input) input.blur(); }
      closePopovers();
    }
  });

  // ---- Filter forms: <form data-autosubmit> submits when a select changes ----------
  document.addEventListener("change", function (event) {
    var form = event.target.closest("form[data-autosubmit]");
    if (form && event.target.matches("select, input[type=checkbox]")) form.requestSubmit();
  });

  // ---- Confirm buttons: <button data-confirm="Are you sure?"> ----------------------
  document.addEventListener("submit", function (event) {
    // Leaving a shared computer: don't leave recently viewed names behind.
    if (/\/logout$/.test(event.target.getAttribute("action") || "")) clearRecents();
    var submitter = event.submitter;
    var message = submitter && submitter.getAttribute("data-confirm");
    if (message && !window.confirm(message)) event.preventDefault();
  });

  // ---- Steady bottom bar ---------------------------------------------------------
  // iOS Safari's safe-area inset grows when its toolbar collapses and shrinks
  // when it returns, which moved the bar up and down while scrolling. Keep the
  // largest inset this device has reported, so the gap only ever grows, and
  // remember it so later page loads start there (theme.js applies it).
  var probe = document.querySelector("[data-safe-area-probe]");
  if (probe && "ResizeObserver" in window) {
    new ResizeObserver(function () {
      var inset = Math.round(probe.getBoundingClientRect().height);
      var known = parseFloat(getComputedStyle(root).getPropertyValue("--dock-safe-max")) || 0;
      if (inset > known && inset <= 100) {
        root.style.setProperty("--dock-safe-max", inset + "px");
        try {
          localStorage.setItem("dock-safe-max", String(inset));
        } catch (e) {
          /* storage blocked: still steady for this page */
        }
      }
    }).observe(probe);
  }

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", markTheme);
  markTheme();
  saveRecent();
  renderLauncherRecents();
})();
