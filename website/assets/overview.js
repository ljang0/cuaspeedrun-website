/* An explorable overview using the same reviewed records as the public results. */
(() => {
  const figure = document.querySelector("[data-benchmark-explainer]");
  if (!figure) return;
  const datasets = JSON.parse(
    figure.querySelector("[data-overview-data]").textContent,
  );
  const svgNS = "http://www.w3.org/2000/svg";
  const plot = figure.querySelector("[data-overview-scatter]");
  const matrix = figure.querySelector("[data-task-matrix]");
  const agent = figure.querySelector("[data-overview-agent]");
  const readout = figure.querySelector("[data-overview-readout]");
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  let dataset = datasets[0];
  let metric = "time_per_task_sec";
  let selected = dataset.records[0].run_id;
  let points = [];
  let plottedDataset = null;

  function element(tag, attributes = {}, text = "") {
    const node = document.createElementNS(svgNS, tag);
    Object.entries(attributes).forEach(([key, value]) =>
      node.setAttribute(key, value),
    );
    if (text) node.textContent = text;
    return node;
  }
  const title = (record) =>
    [
      record.model,
      record.effort === "not_recorded" ? "" : record.effort,
      record.variant,
    ]
      .filter(Boolean)
      .join(" · ");
  const money = (value) =>
    value == null ? "Not available" : `$${value.toFixed(value < 0.1 ? 3 : 2)}`;
  const visibleRecords = () =>
    dataset.records.filter((record) => Number.isFinite(record[metric]));

  const providers = JSON.parse(
    figure.querySelector("[data-providers]").textContent,
  );
  const providerKey = figure.querySelector("[data-provider-key]");
  // SVG has no z-index: draw a marker last to bring it to the front,
  // restoring focus because moving a focused element blurs it.
  function raise(node) {
    const layer = node.parentNode;
    if (!layer || layer.lastChild === node) return;
    const focused = document.activeElement === node;
    layer.append(node);
    if (focused) node.focus({ preventScroll: true });
  }

  function inspect(id) {
    selected = id;
    const record = dataset.records.find((record) => record.run_id === id);
    if (!record) return;
    agent.value = id;
    points.forEach(({ node, record: point }) => {
      node.classList.toggle("is-selected", point.run_id === id);
      node.classList.toggle(
        "is-related",
        point.model === record.model && point.variant === record.variant,
      );
      node.setAttribute("aria-pressed", String(point.run_id === id));
      node.setAttribute("tabindex", point.run_id === id ? "0" : "-1");
      if (point.run_id === id) raise(node);
    });
    const values = [
      ["Task score", `${(record.performance * 100).toFixed(1)}%`],
      ["Mean task time", `${record.time_per_task_sec.toFixed(1)} s`],
      ["Model cost / task", money(record.cost_usd)],
    ];
    const list = document.createElement("dl");
    values.forEach(([label, value]) => {
      const group = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      group.append(dt, dd);
      list.append(group);
    });
    const costNote = document.createElement("p");
    costNote.textContent =
      record.cost_usd == null
        ? "Model cost was not available for this run."
        : `Cost basis: ${record.cost_label.toLowerCase()}. See the full result for assumptions.`;
    readout.replaceChildren(list, costNote);
  }

  function drawPlot() {
    const records = visibleRecords();
    const width = Math.max(300, Math.round(plot.getBoundingClientRect().width));
    const height = Math.round(plot.getBoundingClientRect().height);
    const left = 43,
      right = 17,
      top = 32,
      bottom = 48;
    const extent = Math.max(...records.map((record) => record[metric]), 0.001);
    const magnitude = 10 ** Math.floor(Math.log10(extent));
    const max = Math.ceil(extent / magnitude) * magnitude;
    const x = (value) => left + (value / max) * (width - left - right);
    const y = (value) => height - bottom - value * (height - top - bottom);
    plot.setAttribute("viewBox", `0 0 ${width} ${height}`);
    plot.setAttribute(
      "aria-label",
      `Measured task score against ${metric === "cost_usd" ? "model cost" : "mean task time"} on ${dataset.label}. Use the agent selector or arrow keys on a point to inspect configurations.`,
    );
    const nodes = [
      element(
        "text",
        { x: left, y: 16, class: "plot-axis-title" },
        "Task score (%)",
      ),
    ];
    [0, 0.25, 0.5, 0.75, 1].forEach((value) => {
      nodes.push(
        element("line", {
          x1: left,
          x2: width - right,
          y1: y(value),
          y2: y(value),
          class: "overview-gridline",
        }),
      );
      nodes.push(
        element(
          "text",
          { x: left - 10, y: y(value) + 4, "text-anchor": "end" },
          String(value * 100),
        ),
      );
    });
    const steps = width < 450 ? 3 : 4;
    for (let i = 0; i <= steps; i++) {
      const value = (max * i) / steps;
      nodes.push(
        element(
          "text",
          { x: x(value), y: height - bottom + 20, "text-anchor": "middle" },
          metric === "cost_usd" ? money(value) : String(Math.round(value)),
        ),
      );
    }
    nodes.push(
      element(
        "text",
        {
          x: (left + width - right) / 2,
          y: height - 5,
          "text-anchor": "middle",
          class: "plot-axis-title",
        },
        metric === "cost_usd"
          ? "Model cost per task ($)"
          : "Mean task time (seconds)",
      ),
    );
    const axis = element("g", { "data-overview-axis": "" });
    axis.append(...nodes);
    const previous = new Map(
      plottedDataset === dataset.name
        ? points.map((point) => [point.record.run_id, point.node])
        : [],
    );
    plottedDataset = dataset.name;
    points = records.map((record, index) => {
      const attributes = {
        class: "overview-point",
        role: "button",
        "aria-label": `${title(record)}: ${(record.performance * 100).toFixed(1)} percent, ${metric === "cost_usd" ? money(record.cost_usd) : record.time_per_task_sec.toFixed(1) + " seconds"}`,
      };
      // Position with a CSS transform so axis changes animate the whole marker.
      const position = `translate(${x(record[metric]).toFixed(1)}px, ${y(record.performance).toFixed(1)}px)`;
      const existing = previous.get(record.run_id);
      const node = existing || element("g", attributes);
      node.style.transform = position;
      if (existing) {
        node.setAttribute("aria-label", attributes["aria-label"]);
        return { node, record };
      }
      const face = element("g", { class: "point-face" });
      face.append(
        element("circle", { r: 9.5 }),
        element("use", { href: `#logo-${record.provider}`, x: -6, y: -6, width: 12, height: 12 }),
      );
      node.append(face);
      node.addEventListener("mouseenter", () => raise(node));
      node.append(element("title", {}, title(record)));
      if (!motion.matches) {
        node.style.setProperty("--i", String(index));
        node.classList.add("is-entering");
        node.addEventListener(
          "animationend",
          () => node.classList.remove("is-entering"),
          { once: true },
        );
      }
      node.addEventListener("click", () => inspect(record.run_id));
      node.addEventListener("focus", () => inspect(record.run_id));
      node.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inspect(record.run_id);
        }
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
          return;
        event.preventDefault();
        const sorted = [...points].sort(
          (a, b) => a.record[metric] - b.record[metric],
        );
        const index = sorted.findIndex((point) => point.node === node);
        const next =
          event.key === "Home"
            ? 0
            : event.key === "End"
              ? sorted.length - 1
              : (index +
                  (event.key === "ArrowRight" ? 1 : -1) +
                  sorted.length) %
                sorted.length;
        sorted[next].node.focus();
      });
      return { node, record };
    });
    const oldAxis = plot.querySelector("[data-overview-axis]");
    if (oldAxis) oldAxis.replaceWith(axis);
    else plot.append(axis);
    let pointLayer = plot.querySelector("[data-overview-points]");
    if (!pointLayer) {
      pointLayer = element("g", { "data-overview-points": "" });
      plot.append(pointLayer);
    }
    // Keep existing circles attached so changing axes animates their positions.
    const visible = new Set(points.map((point) => point.node));
    [...pointLayer.children].forEach((node) => {
      if (!visible.has(node)) node.remove();
    });
    points.forEach(({ node }) => {
      if (node.parentNode !== pointLayer) pointLayer.append(node);
    });
    inspect(selected);
  }

  function update() {
    const records = visibleRecords();
    if (!records.some((record) => record.run_id === selected))
      selected = records[0].run_id;
    agent.replaceChildren(
      ...records.map((record) => {
        const option = document.createElement("option");
        option.value = record.run_id;
        option.textContent = title(record);
        return option;
      }),
    );
    figure.querySelector("[data-selected-count]").textContent =
      dataset.selected_tasks;
    figure.querySelector("[data-eligible-count]").textContent =
      dataset.eligible_tasks;
    matrix.setAttribute(
      "aria-label",
      `${dataset.selected_tasks} selected tasks out of ${dataset.eligible_tasks} eligible ${dataset.label} tasks. Squares show counts, not task identities.`,
    );
    matrix.replaceChildren(
      ...Array.from({ length: dataset.eligible_tasks }, (_, i) =>
        element("rect", {
          x: (i % 20) * 12 + 1,
          y: Math.floor(i / 20) * 12 + 1,
          width: 8,
          height: 8,
          class:
            i < dataset.selected_tasks ? "task-selected" : "task-remaining",
          style: `--i: ${i}`,
        }),
      ),
    );
    // Restart the fill-in so each benchmark switch replays the selection.
    matrix.classList.remove("is-filling");
    if (!motion.matches) {
      void matrix.getBoundingClientRect();
      matrix.classList.add("is-filling");
    }
    figure
      .querySelectorAll("[data-benchmark]")
      .forEach((button) =>
        button.setAttribute(
          "aria-pressed",
          String(button.dataset.benchmark === dataset.name),
        ),
      );
    figure
      .querySelectorAll("[data-metric]")
      .forEach((button) =>
        button.setAttribute(
          "aria-pressed",
          String(button.dataset.metric === metric),
        ),
      );
    const omitted = dataset.records.length - records.length;
    figure.querySelector("[data-plot-instruction]").textContent =
      `Select a point to inspect it; related reasoning settings are highlighted.${omitted ? ` ${omitted} configurations have no available cost.` : ""}`;
    figure.querySelector("[data-overview-link]").href = `/${dataset.href}`;
    const present = [...new Set(records.map((record) => record.provider))];
    providerKey.replaceChildren(
      ...present.map((slug) => {
        const item = document.createElement("li");
        const icon = element("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" });
        icon.append(element("use", { href: `#logo-${slug}` }));
        item.append(icon, providers[slug]);
        return item;
      }),
    );
    drawPlot();
    if (!motion.matches) {
      plot.animate(
        [{ transform: "translateY(5px)" }, { transform: "translateY(0)" }],
        { duration: 280, easing: "ease-out" },
      );
      matrix.animate(
        [{ transform: "translateX(-4px)" }, { transform: "translateX(0)" }],
        { duration: 280, easing: "ease-out" },
      );
    }
  }
  figure.querySelectorAll("[data-benchmark]").forEach((button) =>
    button.addEventListener("click", () => {
      dataset = datasets.find(
        (dataset) => dataset.name === button.dataset.benchmark,
      );
      selected = dataset.records[0].run_id;
      update();
    }),
  );
  figure.querySelectorAll("[data-metric]").forEach((button) =>
    button.addEventListener("click", () => {
      metric = button.dataset.metric;
      update();
    }),
  );
  agent.addEventListener("change", () => inspect(agent.value));
  figure.querySelector("[data-explainer-interactive]").hidden = false;
  update();
  let lastWidth = Math.round(plot.getBoundingClientRect().width);
  if (typeof ResizeObserver !== "undefined")
    new ResizeObserver(() => {
      const width = Math.round(plot.getBoundingClientRect().width);
      if (width === lastWidth) return;
      lastWidth = width;
      drawPlot();
    }).observe(plot);
})();
