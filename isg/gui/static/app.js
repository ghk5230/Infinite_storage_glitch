/* Infinite Storage Glitch — terminal GUI, wired to the Flask API */
"use strict";

const $ = (sel) => document.querySelector(sel);

/* ---------- helpers ---------- */
function fmtBytes(n) {
  if (n < 1024) return n + " B";
  const u = ["KB", "MB", "GB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return n.toFixed(n >= 100 ? 0 : 1) + " " + u[i];
}
const fmtDur = (s) => (s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : s.toFixed(1) + "s");
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clamp01 = (n) => Math.max(0, Math.min(1, Number.isFinite(n) ? n : 0));

/* stable pseudo-random bit for canvas noise */
function bitAt(i) {
  let x = (i ^ 0x5f3759df) * 1103515245 + 12345;
  x = (x >>> 13) ^ x;
  return ((x * 0x27d4eb2d) >>> 15) & 1;
}

/* ---------- animated noise logo ---------- */
(() => {
  const c = $("#logo"), x = c.getContext("2d");
  const draw = () => {
    for (let gy = 0; gy < 8; gy++)
      for (let gx = 0; gx < 8; gx++) {
        const r = Math.random();
        x.fillStyle = r < 0.04 ? "#3dff88" : r < 0.08 ? "#22d3ee" : r < 0.55 ? "#04130a" : "#dfffe9";
        x.fillRect(gx * 5, gy * 5, 5, 5);
      }
  };
  draw();
  setInterval(draw, 160);
})();

/* ---------- tabs ---------- */
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => {
    const show = p.id === "panel-" + name;
    p.classList.toggle("hidden", !show);
    if (show) { p.style.animation = "none"; void p.offsetWidth; p.style.animation = ""; }
  });
}
document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { dismissOverlay(); return; }
  if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
  if (e.key === "1") switchTab("encode");
  if (e.key === "2") switchTab("decode");
  if (e.key === "3") switchTab("stress");
});

/* ---------- drop zones ---------- */
function setupDrop(dropId, inputId, chipId, onChange) {
  const drop = $(dropId), input = $(inputId), chip = $(chipId);
  let file = null;
  const update = (f) => {
    file = f;
    drop.classList.toggle("hidden", !!f);
    chip.classList.toggle("hidden", !f);
    if (f) {
      chip.querySelector(".fc-name").textContent = f.name;
      chip.querySelector(".fc-size").textContent = fmtBytes(f.size);
    }
    onChange(f);
  };
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") input.click(); });
  input.addEventListener("change", () => update(input.files[0] || null));
  ["dragover", "dragenter"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) update(e.dataTransfer.files[0]);
  });
  chip.querySelector(".fc-x").addEventListener("click", () => { input.value = ""; update(null); });
  return { get file() { return file; }, clear: () => update(null) };
}

document.querySelectorAll(".pw-eye").forEach((btn) => {
  btn.addEventListener("click", () => {
    const inp = $("#" + btn.dataset.for);
    const show = inp.type === "password";
    inp.type = show ? "text" : "password";
    btn.textContent = show ? "HIDE" : "SHOW";
  });
});

/* ---------- job overlay + canvas viz ---------- */
const overlay = $("#overlay"), viz = $("#viz"), vzx = viz.getContext("2d");
let vizMode = null, vizProgress = 0, vizIndet = false, vizRaf = 0, dismissed = false;

function drawViz(t) {
  const b = 8, cols = viz.width / b, rows = viz.height / b, total = cols * rows;
  const p = vizIndet ? (t / 4000) % 1 : clamp01(vizProgress);
  if (vizMode === "encode") {
    const filled = Math.min(total - 1, Math.floor(total * p));
    for (let i = 0; i < total; i++) {
      const r = Math.floor(i / cols), c = i % cols;
      if (i < filled) vzx.fillStyle = bitAt(i) ? "#e8e8e8" : "#0a0a0a";
      else if (i < filled + cols * 1.5) vzx.fillStyle = Math.random() < 0.5 ? "#124a28" : "#031008";
      else vzx.fillStyle = Math.random() < 0.03 ? "#0d2415" : "#020604";
      vzx.fillRect(c * b, r * b, b, b);
    }
    vzx.fillStyle = "#3dff88";
    vzx.fillRect((filled % cols) * b, Math.floor(filled / cols) * b, b, b);
  } else if (vizMode === "decode") {
    const scanY = Math.floor(rows * p);
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c;
        if (r < scanY) vzx.fillStyle = bitAt(i) ? "#c9f5d6" : "#06120a";
        else vzx.fillStyle = (bitAt(i) ^ (Math.random() < 0.06 ? 1 : 0)) ? "#9a9a9a" : "#141414";
        vzx.fillRect(c * b, r * b, b, b);
      }
    vzx.fillStyle = "rgba(61,255,136,0.9)";
    vzx.fillRect(0, scanY * b, viz.width, 2);
    vzx.fillStyle = "rgba(61,255,136,0.15)";
    vzx.fillRect(0, scanY * b - 14, viz.width, 14);
  } else {
    // stress: crush artifacts ramp up then repair
    const crush = p < 0.4 ? p / 0.4 : Math.max(0, 1 - (p - 0.4) / 0.6);
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c;
        const repaired = p > 0.4 && Math.random() < (p - 0.4) * 1.2;
        vzx.fillStyle = bitAt(i) ? (repaired ? "#c9f5d6" : "#d8d8d8") : (repaired ? "#06120a" : "#101010");
        vzx.fillRect(c * b, r * b, b, b);
      }
    const nBlocks = Math.floor(crush * 46);
    for (let k = 0; k < nBlocks; k++) {
      const bx = Math.floor(Math.random() * cols) * b, by = Math.floor(Math.random() * rows) * b;
      const g = Math.floor(60 + Math.random() * 120);
      vzx.fillStyle = `rgb(${g},${g},${g})`;
      vzx.fillRect(bx, by, b * (1 + Math.floor(Math.random() * 3)), b * (1 + Math.floor(Math.random() * 2)));
    }
  }
  vizRaf = requestAnimationFrame(drawViz);
}

function showOverlay(mode, title) {
  vizMode = mode; vizProgress = 0; vizIndet = false; dismissed = false;
  $("#ov-title").textContent = title;
  $("#ov-phase").textContent = "starting";
  $("#ov-pct").textContent = "0%";
  $("#bar-fill").style.width = "0%";
  $("#bar-fill").classList.remove("indet");
  overlay.classList.remove("hidden");
  cancelAnimationFrame(vizRaf);
  vizRaf = requestAnimationFrame(drawViz);
}
function hideOverlay() {
  overlay.classList.add("hidden");
  cancelAnimationFrame(vizRaf);
}
function dismissOverlay() {
  // job keeps running server-side; this just stops watching it
  if (!overlay.classList.contains("hidden")) { dismissed = true; hideOverlay(); }
}
$("#btn-abort").addEventListener("click", dismissOverlay);

/* ---------- job runner (real API) ---------- */
const OV_TITLES = {
  encode: "ENCODING — FILE → VIDEO",
  decode: "DECODING — VIDEO → FILE",
  stress: "STRESS TEST — YOUTUBE-GRADE CRUSH",
};

async function readApiError(resp) {
  const type = resp.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    const payload = await resp.json().catch(() => ({}));
    return payload.error || resp.statusText || "request failed";
  }
  return (await resp.text()).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
    || resp.statusText || "request failed";
}

async function runJob(mode, url, formData, ui) {
  ui.error.classList.add("hidden");
  ui.result.classList.add("hidden");
  ui.button.disabled = true;
  showOverlay(mode, OV_TITLES[mode]);
  try {
    const resp = await fetch(url, { method: "POST", body: formData });
    if (!resp.ok) throw new Error(await readApiError(resp));
    const { job } = await resp.json();
    while (true) {
      if (dismissed) return null;
      const jobResp = await fetch("/api/job/" + job);
      if (!jobResp.ok) throw new Error(await readApiError(jobResp));
      const j = await jobResp.json();
      $("#ov-phase").textContent = j.phase || "";
      const fill = $("#bar-fill");
      if (j.progress < 0) {
        vizIndet = true;
        fill.classList.add("indet");
        $("#ov-pct").textContent = "···";
      } else {
        vizIndet = false;
        vizProgress = clamp01(Number(j.progress));
        fill.classList.remove("indet");
        fill.style.width = (vizProgress * 100).toFixed(0) + "%";
        $("#ov-pct").textContent = (vizProgress * 100).toFixed(0) + "%";
      }
      if (j.status === "done") return { job, ...j.result };
      if (j.status === "error") throw new Error(j.error);
      await new Promise((r) => setTimeout(r, 400));
    }
  } catch (e) {
    ui.error.textContent = e.message;
    ui.error.classList.remove("hidden");
    return null;
  } finally {
    hideOverlay();
    ui.button.disabled = false;
    updateButtons();
  }
}

function shaRow(hex) {
  return `<div class="sha-row"><span class="lbl">SHA-256</span><span class="hash">${esc(hex)}</span>
    <button class="copy-btn" data-hash="${esc(hex)}">COPY</button></div>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest(".copy-btn");
  if (b) {
    navigator.clipboard.writeText(b.dataset.hash);
    b.textContent = "COPIED!";
    setTimeout(() => (b.textContent = "COPY"), 1200);
  }
});

const stat = (k, v) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`;

/* ---------- ENCODE ---------- */
let lastEncode = null;

const encodeDrop = setupDrop("#drop-encode", "#file-encode", "#chip-encode", updateButtons);
const decodeDrop = setupDrop("#drop-decode", "#file-decode", "#chip-decode", updateButtons);
const stressDrop = setupDrop("#drop-stress", "#file-stress", "#chip-stress", (f) => {
  if (f) { useLast = false; $("#use-last").classList.remove("selected"); }
  updateButtons();
});

document.querySelectorAll("#seg-block, #seg-res, #seg-bitrate").forEach((seg) =>
  seg.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    seg.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    if (seg.id === "seg-bitrate")
      $("#stress-cmd").textContent = "$ isg simulate --bitrate " + b.dataset.v;
  }));

$("#btn-encode").addEventListener("click", async () => {
  const fd = new FormData();
  fd.append("file", encodeDrop.file);
  fd.append("block", document.querySelector("#seg-block button.active").dataset.v);
  fd.append("res", document.querySelector("#seg-res button.active").dataset.v);
  fd.append("password", $("#pw-encode").value);
  const ui = { button: $("#btn-encode"), error: $("#err-encode"), result: $("#res-encode") };
  const r = await runJob("encode", "/api/encode", fd, ui);
  if (!r) return;
  lastEncode = r;
  $("#use-last").classList.remove("hidden");
  $("#use-last .lc-name").textContent = r.file_name;
  ui.result.innerHTML = `
    <div class="badge small"><span class="mark">▣</span>
      <div><h3>ENCODED — ${esc(r.file_name)}</h3>
      <p>self-bootstrapping header · RS(255,223) · byte-interleaved${r.encrypted ? " · aes-256-gcm encrypted" : ""}</p></div></div>
    <div class="stats c5">
      ${stat("ORIGINAL", fmtBytes(r.input_bytes))}
      ${stat("VIDEO", fmtBytes(r.video_bytes))}
      ${stat("FRAMES", r.total_frames.toLocaleString())}
      ${stat("DURATION", fmtDur(r.duration_s))}
      ${stat("ENCRYPTION", r.encrypted ? "AES-256" : "none")}
    </div>
    ${shaRow(r.sha256)}
    <video controls muted src="/api/file/${r.job}"></video>
    <div class="note">▸ this noise IS your file</div>
    <div class="actions">
      <a class="pri" href="/api/file/${r.job}?dl=1" download>⬇ DOWNLOAD VIDEO</a>
      <button class="ghost" id="goto-stress">STRESS-TEST IT →</button>
    </div>`;
  ui.result.classList.remove("hidden");
  $("#goto-stress").addEventListener("click", () => { switchTab("stress"); selectLastEncode(); });
});

/* ---------- DECODE ---------- */
$("#btn-decode").addEventListener("click", async () => {
  const fd = new FormData();
  fd.append("file", decodeDrop.file);
  fd.append("password", $("#pw-decode").value);
  const ui = { button: $("#btn-decode"), error: $("#err-decode"), result: $("#res-decode") };
  const r = await runJob("decode", "/api/decode", fd, ui);
  if (!r) return;
  const badge = r.sha256_ok
    ? `<div class="badge"><span class="mark">✓</span>
        <div><h3>SHA-256 VERIFIED — RECOVERED PERFECTLY</h3>
        <p>every bit survived the trip${r.encrypted ? ", decrypted with aes-256" : ""}</p></div></div>`
    : `<div class="badge warn"><span class="mark">⚠</span>
        <div><h3>CHECKSUM MISMATCH</h3>
        <p>the file was written, but some bytes may be corrupted</p></div></div>`;
  ui.result.innerHTML = `
    ${badge}
    <div class="stats c3">
      ${stat("FILE", esc(r.file_name))}
      ${stat("SIZE", fmtBytes(r.bytes))}
      ${stat("BLOCK SIZE", r.block + " px")}
    </div>
    <div class="actions">
      <a class="pri" href="/api/file/${r.job}?dl=1" download>⬇ DOWNLOAD ${esc(r.file_name)}</a>
    </div>`;
  ui.result.classList.remove("hidden");
});

/* ---------- STRESS ---------- */
let useLast = false;
function selectLastEncode() {
  useLast = true;
  stressDrop.clear();
  $("#use-last").classList.add("selected");
  updateButtons();
}
$("#use-last").addEventListener("click", selectLastEncode);

function updateButtons() {
  $("#btn-encode").disabled = !encodeDrop.file;
  $("#btn-decode").disabled = !decodeDrop.file;
  $("#btn-stress").disabled = !(useLast && lastEncode) && !stressDrop.file;
}
updateButtons();

$("#btn-stress").addEventListener("click", async () => {
  const fd = new FormData();
  if (stressDrop.file) fd.append("file", stressDrop.file);
  else fd.append("source_job", lastEncode.job);
  const bitrate = document.querySelector("#seg-bitrate button.active").dataset.v;
  fd.append("bitrate", bitrate);
  const ui = { button: $("#btn-stress"), error: $("#err-stress"), result: $("#res-stress") };
  const r = await runJob("stress", "/api/stress", fd, ui);
  if (!r) return;
  const human = { "4M": "4 Mbps", "2M": "2 Mbps", "1500k": "1.5 Mbps", "1M": "1 Mbps" }[r.bitrate] || r.bitrate;
  const verdict = r.survived
    ? `<div class="verdict ok"><h2>SURVIVED</h2>
        <p>crushed to ${human} · decoded · sha-256 matches — bit-perfect recovery</p></div>`
    : `<div class="verdict bad"><h2>DESTROYED</h2>
        <p>${esc(r.reason || "the data did not survive this compression level")}</p></div>`;
  ui.result.innerHTML = `
    ${verdict}
    <div class="stats c3">
      ${stat("BITRATE", human)}
      ${stat("BEFORE", fmtBytes(r.original_bytes))}
      ${stat("AFTER CRUSH", fmtBytes(r.degraded_bytes))}
    </div>
    <video controls muted src="/api/file/${r.job}"></video>
    <div class="actions">
      <a class="pri" href="/api/file/${r.job}?dl=1" download>⬇ DOWNLOAD CRUSHED VIDEO</a>
    </div>`;
  ui.result.classList.remove("hidden");
});

/* ---------- footer ---------- */
$("#open-folder").addEventListener("click", () => fetch("/api/open-folder", { method: "POST" }));
