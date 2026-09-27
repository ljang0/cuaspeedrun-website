(() => {
  const root = document.documentElement;
  const toggle = document.querySelector("[data-theme-switch]");
  function theme(value) {
    root.dataset.theme = value;
    if (toggle) {
      toggle.textContent = value === "dark" ? "Light theme" : "Dark theme";
      toggle.setAttribute(
        "aria-label",
        `Switch to ${value === "dark" ? "light" : "dark"} theme`,
      );
    }
  }
  try {
    theme(localStorage.getItem("cua-theme") === "dark" ? "dark" : "light");
  } catch {
    theme("light");
  }
  toggle?.addEventListener("click", () => {
    theme(root.dataset.theme === "dark" ? "light" : "dark");
    try {
      localStorage.setItem("cua-theme", root.dataset.theme);
    } catch {
      /* storage is optional */
    }
  });
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(
          button.parentElement.querySelector("code").textContent,
        );
        button.textContent = "Copied";
      } catch {
        button.textContent = "Select text to copy";
      }
      setTimeout(() => {
        button.textContent = "Copy";
      }, 2500);
    });
  });
  document
    .querySelector("[data-dataset-select]")
    ?.addEventListener("change", (event) => {
      location.assign(event.target.value);
    });

  // Content remains visible without JS, IntersectionObserver, or animation support.
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  if (!motion.matches && typeof IntersectionObserver !== "undefined") {
    const reveal = new IntersectionObserver(
      (entries) => {
        entries.forEach(({ target, isIntersecting }) => {
          if (!isIntersecting) return;
          if (!motion.matches)
            target.animate(
              [
                { transform: "translateY(14px)" },
                { transform: "translateY(0)" },
              ],
              { duration: 460, easing: "cubic-bezier(.2,.65,.3,1)" },
            );
          reveal.unobserve(target);
        });
      },
      { threshold: 0.08 },
    );
    document.querySelectorAll("[data-reveal]").forEach((element) => {
      // Avoid stacking entrance animations on a figure and its containing section.
      if (!element.parentElement.closest("[data-reveal]"))
        reveal.observe(element);
    });
  }

  const figures = document.querySelectorAll("[data-figure-zoom]");
  if (figures.length && typeof HTMLDialogElement !== "undefined") {
    const dialog = document.createElement("dialog");
    dialog.className = "figure-dialog";
    dialog.setAttribute("aria-label", "Enlarged research figure");
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "Close figure";
    const controls = document.createElement("div");
    controls.className = "figure-controls";
    const zoom = document.createElement("button");
    zoom.type = "button";
    zoom.textContent = "Zoom in";
    zoom.setAttribute("aria-pressed", "false");
    controls.append(zoom, close);
    const scroll = document.createElement("div");
    scroll.className = "figure-scroll";
    const image = document.createElement("img");
    scroll.append(image);
    zoom.addEventListener("click", () => {
      const enlarged = dialog.classList.toggle("is-zoomed");
      zoom.textContent = enlarged ? "Fit figure" : "Zoom in";
      zoom.setAttribute("aria-pressed", String(enlarged));
    });
    const caption = document.createElement("p");
    dialog.append(controls, scroll, caption);
    document.body.append(dialog);
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () =>
      document.body.classList.remove("figure-open"),
    );
    figures.forEach((link) =>
      link.addEventListener("click", (event) => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)
          return;
        event.preventDefault();
        dialog.classList.remove("is-zoomed");
        zoom.textContent = "Zoom in";
        zoom.setAttribute("aria-pressed", "false");
        image.src = link.href;
        image.alt = link.querySelector("img").alt;
        caption.textContent = link
          .closest("figure")
          .querySelector("figcaption")
          .textContent.replace("Figure PDF", "")
          .trim();
        document.body.classList.add("figure-open");
        dialog.showModal();
      }),
    );
  }
  // Footer: how long this page actually took to load.
  const loadTime = document.querySelector("[data-load-time]");
  if (loadTime)
    addEventListener("load", () =>
      setTimeout(() => {
        const [entry] = performance.getEntriesByType?.("navigation") || [];
        const ms = entry?.loadEventEnd || performance.now();
        loadTime.textContent = `· this page loaded in ${(ms / 1000).toFixed(2)} s`;
        loadTime.hidden = false;
      }),
    );

  // Article contents double as reading splits; best times stay in this browser.
  const contents = document.querySelector(".page-paper .contents-nav");
  if (contents) {
    const clock = (s) =>
      `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
    let best = {};
    try {
      best = JSON.parse(localStorage.getItem("cua-reading-splits")) || {};
    } catch {
      /* storage is optional */
    }
    const run = document.createElement("p");
    run.className = "reading-run";
    run.innerHTML = "Your reading run <span>0:00</span>";
    const total = run.querySelector("span");
    contents.prepend(run);
    const links = [...contents.querySelectorAll("a[href^='#']")];
    const splits = new Map(
      links.map((link) => {
        const span = document.createElement("span");
        span.className = "read-split";
        span.setAttribute("aria-hidden", "true");
        link.append(span);
        return [link.hash.slice(1), span];
      }),
    );
    const started = performance.now();
    const last = links.at(-1).hash.slice(1);
    const timer = setInterval(() => {
      total.textContent = clock((performance.now() - started) / 1000);
    }, 1000);
    // A section counts as reached once its top passes 40% of the viewport,
    // so skipping ahead still records every section in between.
    const pending = [...splits.keys()]
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    function check() {
      while (pending.length && pending[0].getBoundingClientRect().top < innerHeight * 0.4) {
        const target = pending.shift();
        const span = splits.get(target.id);
        const seconds = (performance.now() - started) / 1000;
        span.textContent = clock(seconds);
        span.classList.add("is-set");
        if (best[target.id] != null && seconds < best[target.id]) {
          span.classList.add("is-best");
          span.title = "Faster than your previous best";
        }
        best[target.id] = Math.min(seconds, best[target.id] ?? Infinity);
        if (target.id === last) {
          clearInterval(timer);
          total.textContent = `${clock(seconds)} ✓`;
          removeEventListener("scroll", onScroll);
        }
      }
      try {
        localStorage.setItem("cua-reading-splits", JSON.stringify(best));
      } catch {
        /* storage is optional */
      }
    }
    let queued = false;
    function onScroll() {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        check();
      });
    }
    addEventListener("scroll", onScroll, { passive: true });
    check();
  }

  // Section headings get a copyable link on hover.
  document.querySelectorAll(".article-body section[id] > h2").forEach((heading) => {
    const link = document.createElement("a");
    link.className = "heading-link";
    link.href = `#${heading.parentElement.id}`;
    link.setAttribute("aria-label", `Link to ${heading.textContent.trim()}`);
    link.textContent = "#";
    heading.append(link);
  });

  document.querySelectorAll("[data-site-nav]").forEach((nav) => {
    nav.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      const links = [...nav.querySelectorAll("a")];
      const index = links.indexOf(document.activeElement);
      if (index < 0) return;
      e.preventDefault();
      const next =
        e.key === "Home"
          ? 0
          : e.key === "End"
            ? links.length - 1
            : (index + (e.key === "ArrowRight" ? 1 : -1) + links.length) %
              links.length;
      links[next].focus();
    });
  });
})();
