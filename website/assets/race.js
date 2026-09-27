/* Homepage race: each lane replays a configuration's measured mean task time.
   Without JS the lanes render in their finished state. */
(() => {
  const race = document.querySelector("[data-race]");
  if (!race) return;
  const list = race.querySelector("[data-race-lanes]");
  const clock = race.querySelector("[data-race-clock]");
  const speedLabel = race.querySelector("[data-race-speed-label]");
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const lanes = [...list.children].map((node, index) => {
    const time = Number(node.dataset.time);
    const steps = Number(node.dataset.steps) || 0;
    const marks = node.querySelector(".lane-marks");
    // One tick per whole step, spaced evenly across the lane.
    const ticks = Array.from({ length: Math.floor(steps) }, (_, k) => {
      const tick = document.createElement("i");
      tick.style.left = `${((k + 1) / steps) * 100}%`;
      marks.append(tick);
      return { at: (k + 1) / steps, node: tick };
    });
    return {
      node,
      index,
      time,
      score: Number(node.dataset.score),
      ticks,
      cursor: node.querySelector(".lane-cursor"),
      shown: 0,
      done: false,
    };
  });
  const end = Math.max(...lanes.map((lane) => lane.time));
  let speed = Number(race.dataset.speed);
  let elapsed = end;
  let last = 0;
  let frame = 0;

  const format = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const rest = (seconds - minutes * 60).toFixed(2).padStart(5, "0");
    return `${minutes}:${rest}`;
  };

  function draw() {
    clock.textContent = format(Math.min(elapsed, end));
    lanes.forEach((lane) => {
      const p = Math.min(1, elapsed / lane.time);
      lane.node.style.setProperty("--p", p.toFixed(4));
      while (lane.shown < lane.ticks.length && lane.ticks[lane.shown].at <= p + 1e-9) {
        lane.ticks[lane.shown++].node.classList.add("is-on");
        lane.cursor.animate(
          [{ transform: "scale(.7) rotate(-8deg)" }, { transform: "none" }],
          { duration: 180, easing: "ease-out" },
        );
      }
      if (p >= 1 && !lane.done) {
        lane.done = true;
        lane.node.classList.add("is-done");
      }
    });
  }

  function tick(now) {
    // Clamp the step so a backgrounded tab does not jump to the finish.
    elapsed += (Math.min(now - last, 100) / 1000) * speed;
    last = now;
    draw();
    if (elapsed < end) frame = requestAnimationFrame(tick);
    else race.classList.remove("is-running");
  }

  function start() {
    cancelAnimationFrame(frame);
    elapsed = 0;
    lanes.forEach((lane) => {
      lane.done = false;
      lane.shown = 0;
      lane.node.classList.remove("is-done");
      lane.ticks.forEach((t) => t.node.classList.remove("is-on"));
    });
    draw();
    race.classList.add("is-running");
    last = performance.now();
    frame = requestAnimationFrame(tick);
  }

  function finish() {
    elapsed = end;
    lanes.forEach((lane) => {
      lane.shown = lane.ticks.length;
      lane.ticks.forEach((t) => t.node.classList.add("is-on"));
    });
    draw();
  }

  function sort(order) {
    const key = {
      lineup: (a, b) => a.index - b.index,
      time: (a, b) => a.time - b.time,
      score: (a, b) => b.score - a.score || a.time - b.time,
    }[order];
    const before = new Map(lanes.map((l) => [l, l.node.getBoundingClientRect().top]));
    list.append(...[...lanes].sort(key).map((l) => l.node));
    if (motion.matches) return;
    lanes.forEach((l) => {
      const dy = before.get(l) - l.node.getBoundingClientRect().top;
      if (dy)
        l.node.animate(
          [{ transform: `translateY(${dy}px)` }, { transform: "none" }],
          { duration: 520, easing: "cubic-bezier(.3,1.35,.5,1)" },
        );
    });
  }

  function press(selector, button) {
    race.querySelectorAll(selector).forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
  }
  race.querySelector("[data-race-replay]").addEventListener("click", start);
  race.querySelectorAll("[data-race-speed]").forEach((button) =>
    button.addEventListener("click", () => {
      speed = Number(button.dataset.raceSpeed);
      speedLabel.textContent = `${speed}×`;
      press("[data-race-speed]", button);
      start();
    }),
  );
  race.querySelectorAll("[data-race-sort]").forEach((button) =>
    button.addEventListener("click", () => {
      press("[data-race-sort]", button);
      sort(button.dataset.raceSort);
    }),
  );
  race.querySelector("[data-race-controls]").hidden = false;
  finish();

  if (!motion.matches && typeof IntersectionObserver !== "undefined") {
    const watch = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        watch.disconnect();
        start();
      },
      { threshold: 0.35 },
    );
    watch.observe(list);
  }
})();
