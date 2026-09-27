/* Public results table: developer logos, value bars, podium ranks, and rows
   that glide to their new place when the ranking changes. The shared
   leaderboard script still owns filtering and ordering. */
(() => {
  const root = document.querySelector("[data-results-dashboard]");
  if (!root || !root.dataset.defaultView) return;
  const body = root.querySelector("[data-results-body]");
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const svgNS = "http://www.w3.org/2000/svg";
  let prefixes = [];
  try {
    prefixes = JSON.parse(document.querySelector("[data-provider-prefixes]").textContent);
  } catch {
    /* logos are optional */
  }
  // Record board numbers count up from zero once.
  document.querySelectorAll("[data-count-to]").forEach((node) => {
    if (motion.matches) return;
    const target = Number(node.dataset.countTo);
    const decimals = Number(node.dataset.decimals) || 0;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / 1100);
      node.textContent = (target * (1 - (1 - t) ** 3)).toFixed(decimals);
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });

  const rows = [...body.rows];
  const value = (row, key) => (row.dataset[key] === "" ? NaN : Number(row.dataset[key]));
  const max = (key) => Math.max(...rows.map((row) => value(row, key)).filter(Number.isFinite));
  const scale = { time: max("time"), cost: max("cost") };

  rows.forEach((row) => {
    const developer = prefixes.find((p) => row.dataset.model.startsWith(p.prefix));
    const swatch = row.querySelector(".model-swatch");
    if (developer && swatch) {
      const logo = document.createElementNS(svgNS, "svg");
      logo.setAttribute("viewBox", "0 0 24 24");
      logo.setAttribute("role", "img");
      logo.setAttribute("aria-label", developer.name);
      const use = document.createElementNS(svgNS, "use");
      use.setAttribute("href", `#logo-${developer.slug}`);
      logo.append(use);
      swatch.replaceChildren(logo);
      swatch.classList.add("has-logo");
    }
    // Bars start empty and grow once the table is first drawn.
    const bars = [
      [".performance-cell", value(row, "performance")],
      [".time-cell", value(row, "time") / scale.time],
      [".cost-cell", value(row, "cost") / scale.cost],
    ];
    bars.forEach(([selector, v]) => {
      const cell = row.querySelector(selector);
      if (!cell) return;
      cell.classList.add("has-bar");
      cell.dataset.v = Number.isFinite(v) ? v.toFixed(4) : "0";
      cell.style.setProperty("--v", motion.matches ? cell.dataset.v : "0");
    });
  });

  let before = null;
  // Record row positions before the shared script reorders them.
  const remember = () => {
    before = new Map(rows.filter((row) => !row.hidden).map((row) => [row, row.getBoundingClientRect().top]));
  };
  root.addEventListener("click", (event) => {
    if (event.target.closest("[data-ranking], [data-reset-filters], [data-access]")) remember();
  }, true);
  root.addEventListener("change", remember, true);

  let first = true;
  root.addEventListener("results:table", (event) => {
    const ranking = event.detail.ranking;
    root.dataset.rankedBy = ranking;
    const visible = rows.filter((row) => !row.hidden)
      .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
    rows.forEach((row) => row.classList.remove("is-gold", "is-silver", "is-bronze", "is-wr"));
    ["is-gold", "is-silver", "is-bronze"].forEach((name, i) => visible[i]?.classList.add(name));
    if (ranking === "time" && visible[0]) {
      visible[0].classList.add("is-wr");
      visible[0].querySelector("[data-rank]").title = "Fastest mean task time in this set";
    }
    if (motion.matches) return;
    if (first) {
      first = false;
      // Stagger the first appearance, then grow the bars.
      visible.forEach((row, i) => {
        if (i < 24)
          row.animate([{ transform: "translateX(-10px)" }, { transform: "none" }], {
            duration: 420, delay: i * 22, easing: "cubic-bezier(.2,.7,.3,1)", fill: "backwards",
          });
      });
      requestAnimationFrame(() => requestAnimationFrame(() =>
        rows.forEach((row) => row.querySelectorAll(".has-bar").forEach((cell) =>
          cell.style.setProperty("--v", cell.dataset.v)))));
      return;
    }
    if (!before) return;
    visible.forEach((row) => {
      const was = before.get(row);
      const dy = was == null ? 0 : was - row.getBoundingClientRect().top;
      if (was == null)
        row.animate([{ transform: "scale(.98)" }, { transform: "none" }], { duration: 300 });
      else if (Math.abs(dy) > 1)
        row.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], {
          duration: 560, easing: "cubic-bezier(.3,1.25,.5,1)",
        });
    });
    before = null;
  });
})();
