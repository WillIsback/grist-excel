/* grist-excel web UI — vanilla JS, no framework */

const $ = id => document.getElementById(id);

// ── Screens ──────────────────────────────────────────────────────────────────
function showScreen(name) {
  document.querySelectorAll(".screen").forEach(s => s.classList.add("hidden"));
  const el = document.querySelector(`.screen[data-screen="${name}"]`);
  if (el) el.classList.remove("hidden");
}

// ── Upload screen ─────────────────────────────────────────────────────────────
let selectedFile = null;

function initUpload() {
  const zone = $("drop-zone");
  const fileInput = $("file-input");
  const filename = $("filename");
  const analyseBtn = $("analyse-btn");

  zone.addEventListener("click", () => fileInput.click());
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("over");
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) setFile(fileInput.files[0]);
  });
  analyseBtn.addEventListener("click", startAnalysis);

  function setFile(f) {
    if (!f.name.endsWith(".xlsx")) {
      alert("Seuls les fichiers .xlsx sont acceptés.");
      return;
    }
    if (f.size > 50 * 1024 * 1024) {
      alert("Fichier trop volumineux (max 50 Mo).");
      return;
    }
    selectedFile = f;
    filename.textContent = f.name;
    analyseBtn.disabled = false;
  }
}

async function startAnalysis() {
  if (!selectedFile) return;
  const form = new FormData();
  form.append("file", selectedFile);

  const resp = await fetch("/upload", { method: "POST", body: form });
  if (!resp.ok) { alert("Erreur lors de l'envoi du fichier."); return; }
  const { session_id } = await resp.json();

  window.location.href = `/run?sid=${session_id}`;
}

// ── Run screen ────────────────────────────────────────────────────────────────
function setStepperState(activeIndex) {
  document.querySelectorAll(".step").forEach((el, i) => {
    el.classList.toggle("done",   i < activeIndex);
    el.classList.toggle("active", i === activeIndex);
  });
}

function setProgress(pct) {
  const bar = $("progress-bar");
  if (bar) bar.style.width = pct + "%";
}

function setLog(msg) {
  const el = $("log-line");
  if (el) el.textContent = msg;
}

function initRun() {
  const params = new URLSearchParams(window.location.search);
  const sid = params.get("sid");
  if (!sid) { showScreen("error"); $("error-msg").textContent = "Session manquante."; return; }

  window._sid = sid;
  showScreen("progress");
  setStepperState(0);

  const es = new EventSource(`/stream/${sid}`);

  es.addEventListener("step", e => {
    const d = JSON.parse(e.data);
    setLog(d.message);
    setProgress(d.pct || 0);
    if (d.pct >= 25) setStepperState(1);
    if (d.pct >= 65) setStepperState(3);
    if (d.pct >= 85) setStepperState(4);
  });

  es.addEventListener("checkpoint_1", e => {
    const d = JSON.parse(e.data);
    showCheckpoint1(d);
    es.close();
  });

  es.addEventListener("checkpoint_2", e => {
    const d = JSON.parse(e.data);
    showCheckpoint2(d);
    es.close();
  });

  es.addEventListener("complete", e => {
    const d = JSON.parse(e.data);
    es.close();
    showResult(d);
  });

  es.addEventListener("error", e => {
    const d = JSON.parse(e.data || '{"message":"Erreur inconnue."}');
    es.close();
    showScreen("error");
    $("error-msg").textContent = d.message;
  });
}

// ── Checkpoint 1 ──────────────────────────────────────────────────────────────
function showCheckpoint1(data) {
  setStepperState(2);
  const container = $("cp1-archetypes");
  container.innerHTML = "";
  data.archetypes.forEach(a => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "archetype";
    input.value = a;
    if (a === data.archetype) input.checked = true;
    label.appendChild(input);
    label.appendChild(document.createTextNode(" " + a));
    container.appendChild(label);
  });

  $("cp1-confidence").textContent = `Confiance : ${Math.round(data.confidence * 100)} %`;
  showScreen("checkpoint1");

  $("cp1-form").onsubmit = async e => {
    e.preventDefault();
    const archetype = document.querySelector('input[name="archetype"]:checked')?.value || data.archetype;
    const user_intent = $("cp1-intent").value;
    const form = new FormData();
    form.append("archetype", archetype);
    form.append("user_intent", user_intent);
    await fetch(`/checkpoint1/${window._sid}`, { method: "POST", body: form });
    showScreen("progress");
    resumeStream("checkpoint_2", showCheckpoint2, "complete", showResult);
  };
}

// ── Checkpoint 2 ──────────────────────────────────────────────────────────────
function showCheckpoint2(data) {
  setStepperState(3);
  const list = $("cp2-insights");
  list.innerHTML = "";
  data.insights.forEach(ins => {
    const li = document.createElement("li");
    li.className = "insight-item";
    li.innerHTML = `
      <input type="checkbox" name="insight" value="${ins.index}" checked>
      <div>
        <div>${ins.finding}</div>
        <div class="insight-meta">${ins.type} — ${ins.table}.${ins.col}</div>
      </div>`;
    list.appendChild(li);
  });
  showScreen("checkpoint2");

  $("cp2-form").onsubmit = async e => {
    e.preventDefault();
    const selected = [...document.querySelectorAll('input[name="insight"]:checked')]
      .map(el => parseInt(el.value));
    const form = new FormData();
    form.append("selected_indices", JSON.stringify(selected));
    await fetch(`/checkpoint2/${window._sid}`, { method: "POST", body: form });
    showScreen("progress");
    setStepperState(4);
    resumeStream(null, null, "complete", showResult);
  };
}

// ── Resume SSE after checkpoint ───────────────────────────────────────────────
function resumeStream(cpEvent, cpHandler, doneEvent, doneHandler) {
  const es = new EventSource(`/stream/${window._sid}`);

  if (cpEvent && cpHandler) {
    es.addEventListener(cpEvent, e => {
      const d = JSON.parse(e.data);
      cpHandler(d);
      es.close();
    });
  }

  es.addEventListener(doneEvent, e => {
    const d = JSON.parse(e.data);
    es.close();
    doneHandler(d);
  });

  es.addEventListener("step", e => {
    const d = JSON.parse(e.data);
    setLog(d.message);
    setProgress(d.pct || 0);
  });

  es.addEventListener("error", e => {
    const d = JSON.parse(e.data || '{"message":"Erreur inconnue."}');
    es.close();
    showScreen("error");
    $("error-msg").textContent = d.message;
  });
}

// ── Result screen ─────────────────────────────────────────────────────────────
function showResult(data) {
  setStepperState(5);
  $("result-link").href = data.doc_url;
  const chips = $("page-chips");
  chips.innerHTML = "";
  (data.pages || []).forEach(p => {
    const span = document.createElement("span");
    span.className = "page-chip";
    span.textContent = p;
    chips.appendChild(span);
  });
  showScreen("result");
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  if (document.querySelector('[data-screen="upload"]')) {
    initUpload();
    showScreen("upload");
  } else if (document.querySelector('[data-screen="progress"]')) {
    initRun();
  }
});
