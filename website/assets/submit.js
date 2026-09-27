// Credentials stay in these controls until an authenticated, explicit launch.
// They are never stored in localStorage, URLs, analytics, or console output.
(() => {
  const $ = (id) => document.getElementById(id);
  let templates = [],
    tracks = [],
    benchmarks = [],
    modalConfigured = false,
    ready = false;
  const note = (message) => {
    $("connection-status").textContent = message;
  };
  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(
        "The evaluation service is unavailable. Please try again later.",
      );
    }
    if (!response.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : "The evaluation service could not accept this request.";
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function addKey(name = "") {
    const row = document.createElement("div");
    row.className = "key-row";
    const key = document.createElement("input");
    key.placeholder = "OPENAI_API_KEY";
    key.value = name;
    key.setAttribute("aria-label", "Environment variable name");
    key.pattern = "[A-Za-z_][A-Za-z0-9_]*";
    key.autocomplete = "off";
    key.spellcheck = false;
    const value = document.createElement("input");
    value.type = "password";
    value.placeholder = "API key or value";
    value.autocomplete = "new-password";
    value.setAttribute(
      "aria-label",
      name ? `${name} value` : "Environment variable value",
    );
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", "Remove environment variable");
    remove.addEventListener("click", () => row.remove());
    row.append(key, value, remove);
    $("environment-keys").append(row);
  }
  function options(select, items, value, label) {
    select.replaceChildren(new Option("Select…", ""));
    for (const item of items)
      select.add(new Option(label(item), String(item[value])));
  }
  function summary() {
    const track = tracks.find((t) => t.name === $("track").value);
    const benchmark = benchmarks.find(
      (b) => String(b.id) === $("benchmark").value,
    );
    $("track-help").textContent = track
      ? `${track.eval_algorithm} · ${track.agents_per_evaluation} agents per evaluation · track GPU: ${track.gpu || "none"}. Rankings compare compatible runs within this track.`
      : "Select an evaluation track.";
    $("run-summary").textContent =
      track && benchmark
        ? `${benchmark.name} · ${benchmark.task_count} tasks · ${track.name}. Agent and environment run on Modal. GPU: ${$("allocate-gpu").checked ? track.gpu || "none" : "not allocated"}.`
        : "Select a benchmark and track above.";
  }
  function sourceChanged() {
    const template = templates.find((t) => t.name === $("source").value);
    $("upload-fields").hidden = !!template;
    $("agent-file").required = !template;
    $("template-description").textContent = template
      ? template.description
      : "";
    for (const name of template?.required_environment_variables || []) {
      const present = [
        ...$("environment-keys").querySelectorAll(".key-row input:first-child"),
      ].some((input) => input.value === name);
      if (!present) addKey(name);
    }
  }
  function benchmarkChanged() {
    const previous = $("source").value;
    const benchmark = benchmarks.find(
      (b) => String(b.id) === $("benchmark").value,
    );
    $("source").replaceChildren(new Option("Upload Python files", "upload"));
    for (const t of templates) {
      if (!benchmark || t.compatible_benchmarks.includes(benchmark.name))
        $("source").add(new Option(`Template: ${t.name}`, t.name));
    }
    if ([...$("source").options].some((o) => o.value === previous))
      $("source").value = previous;
    sourceChanged();
    summary();
  }
  $("add-key").addEventListener("click", () => addKey());
  $("source").addEventListener("change", sourceChanged);
  $("benchmark").addEventListener("change", benchmarkChanged);
  $("track").addEventListener("change", summary);
  $("allocate-gpu").addEventListener("change", summary);
  $("evaluation-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    if (!ready || $("launch").disabled) return;
    $("form-message").textContent = "";
    $("launch").disabled = true;
    try {
      const body = new FormData();
      for (const key of ["name", "track", "benchmark_id"])
        body.set(key, new FormData(form).get(key));
      body.set("compute_placement", "modal");
      body.set("environment_placement", "modal");
      body.set("allocate_gpu", String($("allocate-gpu").checked));
      body.set("parallel_evaluations", "1");
      if ($("source").value === "upload") {
        const agent = $("agent-file").files[0],
          init = $("init-file").files[0];
        if (
          !agent ||
          agent.name !== "agent.py" ||
          (init && init.name !== "init.py")
        )
          throw new Error("Name your files agent.py and init.py.");
        if (agent.size + (init?.size || 0) > 1048576)
          throw new Error("The combined files must be no larger than 1 MiB.");
        body.set("agent_file", agent);
        if (init) body.set("init_file", init);
      } else body.set("template", $("source").value);
      const environment = [];
      for (const row of $("environment-keys").children) {
        const [key, value] = row.querySelectorAll("input");
        if (!key.value && !value.value) continue;
        if (!key.value || !value.value)
          throw new Error(
            "Each environment variable needs a name and a value.",
          );
        if (environment.some((item) => item.name === key.value.trim()))
          throw new Error("Use each environment variable name only once.");
        environment.push({ name: key.value.trim(), value: value.value });
      }
      body.set("evaluation_environment_variables", JSON.stringify(environment));
      const id = $("modal-id").value.trim(),
        secret = $("modal-secret").value.trim();
      if (!modalConfigured || id || secret) {
        if (!id.startsWith("ak-") || !secret.startsWith("as-"))
          throw new Error(
            "Enter a complete Modal token pair: ak- ID and as- secret.",
          );
        await api("/api/me/modal-credentials", {
          method: "POST",
          body: new URLSearchParams({ token_id: id, token_secret: secret }),
        });
        modalConfigured = true;
        $("modal-id").value = "";
        $("modal-secret").value = "";
        $("modal-status").textContent =
          "Modal account connected. Leave the fields blank to use the saved credentials.";
      }
      $("launch").textContent = "Submitting…";
      const result = await api("/api/submissions", { method: "POST", body });
      if (!Number.isInteger(result.run_id))
        throw new Error(
          "The service returned an unexpected response. Check account settings for the run before retrying.",
        );
      form.reset();
      location.assign(`/runs/${result.run_id}`);
    } catch (error) {
      $("form-message").textContent = error.message;
    } finally {
      $("launch").disabled = false;
      $("launch").textContent = "Launch evaluation";
    }
  });
  (async () => {
    try {
      const connection = await api("/site-api/status", {
        signal: AbortSignal.timeout(15000),
      });
      if (!connection.configured)
        throw new Error(
          "Hosted evaluations are not open yet. You can run the same toolkit on Modal from the command line.",
        );
      [benchmarks, tracks, templates] = await Promise.all([
        api("/api/benchmarks"),
        api("/api/tracks"),
        api("/api/templates"),
      ]);
      tracks = tracks.filter((t) => !t.reference_only);
      options(
        $("benchmark"),
        benchmarks,
        "id",
        (b) => `${b.name} · ${b.task_count} tasks`,
      );
      options($("track"), tracks, "name", (t) => t.name);
      if (!tracks.length || !benchmarks.length)
        throw new Error(
          "This evaluator has no runnable benchmarks or tracks configured yet.",
        );
      benchmarkChanged();
      $("submit-layout").hidden = false;
      $("account-status").hidden = false;
      let user;
      try {
        user = await api("/api/me");
      } catch (error) {
        if (error.status !== 401) throw error;
        note(
          "Sign in with GitHub to connect your accounts and launch an evaluation.",
        );
        return;
      }
      const credentials = await api("/api/me/modal-credentials");
      modalConfigured = credentials.configured;
      $("sign-in").hidden = true;
      $("signed-in").hidden = false;
      $("signed-in").textContent = `Signed in as ${user.handle}`;
      if (modalConfigured)
        $("modal-status").textContent =
          "Modal account connected. Leave the fields blank to use the saved credentials.";
      document.querySelectorAll("[data-auth-field]").forEach((fieldset) => {
        fieldset.disabled = false;
      });
      ready = true;
      note("Evaluation service connected. Choose a benchmark to get started.");
      $("connection-status").dataset.state = "open";
    } catch (error) {
      note(
        error.name === "TimeoutError"
          ? "The evaluation service did not respond. You can still run the toolkit from the command line."
          : error.message,
      );
      $("connection-status").dataset.state = "closed";
      $("submit-layout").hidden = true;
      $("run-guide").hidden = false;
    }
  })();
})();
