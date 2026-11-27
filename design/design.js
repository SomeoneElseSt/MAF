// design/index.html: the two tabs, the Dark switch, ⌘K search over both tabs, and the Screens grid and viewer.
// Addresses: #design, #screens, #<any id on the page> (a rule, token or component), #screen=<screen id>.
(function () {
  const data = window.MAF_SCREENS || null;
  const screens = data ? data.screens : [];
  const $ = selector => document.querySelector(selector);
  const store = { get: k => { try { return localStorage.getItem(k); } catch { return null; } },
                  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} } };

  // Dark switch, like the site's.
  const themeButton = $("[data-theme-toggle]");
  const isDark = () => (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
  const labelTheme = () => { themeButton.textContent = isDark() ? "Light" : "Dark"; };
  themeButton.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    store.set("theme", next);
    labelTheme();
    if (!store.get("ds-shade")) { state.shade = next; renderScreens(); }
  });
  labelTheme();

  // Tabs. The page widens for Screens.
  function showTab(name) {
    document.querySelectorAll("[data-panel]").forEach(panel => { panel.hidden = panel.dataset.panel !== name; });
    document.querySelectorAll("[data-tab]").forEach(link => link.toggleAttribute("aria-current", link.dataset.tab === name));
    $(".ds-page").classList.toggle("wide", name === "screens");
  }

  function highlight(element) {
    element.scrollIntoView({ block: "start" });
    element.classList.remove("ds-hit", "fade");
    void element.offsetWidth;
    element.classList.add("ds-hit");
    setTimeout(() => element.classList.add("fade"), 50);
    setTimeout(() => element.classList.remove("ds-hit", "fade"), 3500);
  }

  function route() {
    const hash = decodeURIComponent(location.hash.slice(1));
    if (hash.startsWith("screen=")) {
      showTab("screens");
      const card = document.getElementById("screen-" + hash.slice(7));
      if (card) highlight(card);
      return;
    }
    if (hash === "screens") { showTab("screens"); window.scrollTo(0, 0); return; }
    showTab("design");
    const target = hash && hash !== "design" ? document.getElementById(hash) : null;
    if (target) highlight(target);
    else window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);

  // Screens
  const state = {
    device: store.get("ds-device") || "desktop",
    shade: store.get("ds-shade") || (isDark() ? "dark" : "light"),
    group: "All",
  };
  const groups = ["All", ...new Set(screens.map(s => s.group))];
  const variantName = () => `${state.device}-${state.shade}`;

  function pressed() {
    document.querySelectorAll("[data-device]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.device === state.device)));
    document.querySelectorAll("[data-shade]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.shade === state.shade)));
    document.querySelectorAll("[data-group]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.group === state.group)));
  }

  function card(screen) {
    const shot = screen.shots[variantName()];
    const errors = screen.errors.length ? `<p class="ds-errors">${screen.errors.length} problem${screen.errors.length > 1 ? "s" : ""} while taking it: ${escape(screen.errors.join("; "))}</p>` : "";
    return `<article class="ds-card" id="screen-${screen.id}">
      <button class="shot" type="button" data-open="${screen.id}" aria-label="Open ${escape(screen.name)}">${shot ? `<img src="screens/${shot}" alt="" loading="lazy">` : `<span class="missing">Not taken in this view</span>`}</button>
      <h3>${escape(screen.name)}</h3>
      <p>${escape(screen.shows)}</p>
      <p class="ds-id">${screen.id} · as ${screen.who}</p>${errors}
    </article>`;
  }

  function renderScreens() {
    const list = $("#screen-list");
    $("#no-screens").hidden = screens.length > 0;
    if (!screens.length) return;
    $("#taken").textContent = `Taken ${data.taken}, ${screens.length} screens`;
    pressed();
    const shown = groups.filter(g => g !== "All" && (state.group === "All" || state.group === g));
    list.innerHTML = shown.map(group => `<h2 class="ds-group-title">${escape(group)}</h2>
      <div class="ds-grid ${state.device}">${screens.filter(s => s.group === group).map(card).join("")}</div>`).join("");
  }

  $("#groups").innerHTML = groups.map(g => `<button type="button" data-group="${escape(g)}">${escape(g)}</button>`).join("");
  document.addEventListener("click", event => {
    const button = event.target.closest("[data-device], [data-shade], [data-group]");
    if (!button) return;
    if (button.dataset.device) { state.device = button.dataset.device; store.set("ds-device", state.device); }
    if (button.dataset.shade) { state.shade = button.dataset.shade; store.set("ds-shade", state.shade); }
    if (button.dataset.group) state.group = button.dataset.group;
    renderScreens();
  });

  // Viewer: all four views of one screen side by side, with its details.
  const viewer = $("#viewer");
  let viewing = -1;
  function openScreen(id) {
    viewing = screens.findIndex(s => s.id === id);
    if (viewing < 0) return;
    const screen = screens[viewing];
    $("#viewer-title").textContent = screen.name;
    $("#viewer-sub").textContent = `${screen.id} · ${screen.group} · as ${screen.who} · ${screen.path}`;
    const order = ["desktop-light", "phone-light", "desktop-dark", "phone-dark"];
    $("#viewer-shots").innerHTML = order.map(v => screen.shots[v]
      ? `<figure><figcaption>${v.replace("-", ", ")}</figcaption><a href="screens/${screen.shots[v]}" target="_blank"><img src="screens/${screen.shots[v]}" alt="${escape(screen.name)}, ${v}"></a></figure>`
      : `<figure><figcaption>${v.replace("-", ", ")}: not taken</figcaption></figure>`).join("") +
      `<p class="ds-detail" style="grid-column: 1 / -1">${escape(screen.shows)}<br>Made by: ${screen.files.map(escape).join(", ") || "—"}</p>`;
    if (!viewer.open) viewer.showModal();
    history.replaceState(null, "", "#screen=" + screen.id);
  }
  document.addEventListener("click", event => {
    const opener = event.target.closest("[data-open]");
    if (opener) openScreen(opener.dataset.open);
    const step = event.target.closest("[data-step]");
    if (step) openScreen(screens[(viewing + Number(step.dataset.step) + screens.length) % screens.length].id);
    if (event.target.closest("[data-close]")) viewer.close();
  });
  viewer.addEventListener("keydown", event => {
    if (event.key === "ArrowRight") openScreen(screens[(viewing + 1) % screens.length].id);
    if (event.key === "ArrowLeft") openScreen(screens[(viewing - 1 + screens.length) % screens.length].id);
  });

  // ⌘K: one search over the design system (headings, rules, tokens, components) and every screen.
  const index = [];
  document.querySelectorAll("#design [id]").forEach(element => {
    if (element.matches("section#design, input, textarea")) return;
    const section = element.closest(".ds-section");
    const title = element.matches("section") ? element.querySelector("h2")?.textContent : element.matches("h3") ? element.textContent
      : element.querySelector("strong, code")?.textContent || element.textContent.trim().slice(0, 60);
    index.push({ kind: section ? section.querySelector("h2").textContent : "Design system", title: (title || "").trim(),
                 text: element.innerText.replace(/\s+/g, " ").trim(), go: "#" + element.id });
    index[index.length - 1].snippet = index[index.length - 1].text;
  });
  screens.forEach(s => index.push({ kind: "Screen · " + s.group, title: s.name, text: [s.id, s.name, s.shows, s.path, s.who, ...s.files].join(" "), go: "#screen=" + s.id, screen: s.id, snippet: s.shows }));

  const palette = $("#palette"), input = $("#palette-input"), results = $("#palette-results");
  let hits = [], selected = 0;
  function search() {
    const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    hits = words.length ? index.map(item => {
      const title = item.title.toLowerCase(), text = item.text.toLowerCase();
      if (!words.every(w => text.includes(w) || title.includes(w))) return null;
      return { item, score: words.reduce((n, w) => n + (title.includes(w) ? 3 : 1), 0) };
    }).filter(Boolean).sort((a, b) => b.score - a.score || a.item.text.length - b.item.text.length).slice(0, 30).map(h => h.item) : index.filter(i => i.go.startsWith("#") && /^#[a-z]+$/.test(i.go)).slice(0, 12);
    selected = 0;
    results.innerHTML = hits.length ? hits.map((h, i) => `<button type="button" role="option" data-hit="${i}" aria-selected="${i === selected}">${escape(h.title)}<span class="kind">${escape(h.kind)}</span><span class="snippet">${escape(h.snippet.slice(0, 160))}</span></button>`).join("")
      : `<p class="empty">Nothing matches.</p>`;
  }
  function choose(i) {
    const hit = hits[i];
    if (!hit) return;
    palette.close();
    if (location.hash === hit.go) route(); else location.hash = hit.go;
    if (hit.screen) setTimeout(() => openScreen(hit.screen), 50);
  }
  function openPalette() { input.value = ""; search(); palette.showModal(); input.focus(); }
  $(".ds-find").addEventListener("click", openPalette);
  input.addEventListener("input", search);
  results.addEventListener("click", event => { const b = event.target.closest("[data-hit]"); if (b) choose(Number(b.dataset.hit)); });
  input.addEventListener("keydown", event => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      selected = Math.max(0, Math.min(hits.length - 1, selected + (event.key === "ArrowDown" ? 1 : -1)));
      results.querySelectorAll("[data-hit]").forEach((b, i) => b.setAttribute("aria-selected", String(i === selected)));
      results.querySelector(`[data-hit="${selected}"]`)?.scrollIntoView({ block: "nearest" });
    }
    if (event.key === "Enter") { event.preventDefault(); choose(selected); }
  });
  document.addEventListener("keydown", event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (palette.open) palette.close(); else { if (viewer.open) viewer.close(); openPalette(); }
    }
  });
  palette.addEventListener("click", event => { if (event.target === palette) palette.close(); });
  viewer.addEventListener("click", event => { if (event.target === viewer) viewer.close(); });

  function escape(text) {
    return String(text).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  renderScreens();
  route();
})();
