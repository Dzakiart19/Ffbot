const API = "";
let currentUser = null;
let progressInterval = null;

/* ─── PARTICLES ─────────────────────────────── */
function initParticles() {
  const bg = document.getElementById("particles-bg");
  const colors = ["#ff6b00", "#ffd700", "#00d4ff", "#ff2244", "#00ff88"];
  for (let i = 0; i < 30; i++) {
    const p = document.createElement("div");
    p.className = "particle";
    const size = Math.random() * 4 + 2;
    p.style.cssText = `
      width:${size}px; height:${size}px;
      left:${Math.random() * 100}%;
      background:${colors[Math.floor(Math.random() * colors.length)]};
      animation-duration:${Math.random() * 12 + 8}s;
      animation-delay:${Math.random() * 8}s;
    `;
    bg.appendChild(p);
  }
}

/* ─── TOAST ─────────────────────────────────── */
function toast(msg, type = "info") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

/* ─── AUTH ──────────────────────────────────── */
function saveSession(token, user) {
  localStorage.setItem("kios_token", token);
  localStorage.setItem("kios_user", JSON.stringify(user));
  currentUser = user;
  updateUI();
}

function logout() {
  localStorage.removeItem("kios_token");
  localStorage.removeItem("kios_user");
  currentUser = null;
  updateUI();
  toast("Logout berhasil", "info");
}

function getToken() {
  return localStorage.getItem("kios_token");
}

function loadSession() {
  const token = getToken();
  const user = localStorage.getItem("kios_user");
  if (token && user) {
    try {
      currentUser = JSON.parse(user);
      updateUI();
      refreshMe();
    } catch {}
  }
}

async function refreshMe() {
  const token = getToken();
  if (!token) return;
  try {
    const r = await fetch(`${API}/api/me`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (r.ok) {
      const data = await r.json();
      currentUser = data;
      localStorage.setItem("kios_user", JSON.stringify(data));
      updateUI();
    } else if (r.status === 401) {
      logout();
    }
  } catch {}
}

function updateUI() {
  const navBtn = document.getElementById("nav-user-btn");
  const userBar = document.getElementById("user-bar");
  const loginSection = document.getElementById("login-section");

  if (currentUser) {
    navBtn.textContent = currentUser.username;
    userBar.style.display = "block";
    document.getElementById("user-bar-name").innerHTML =
      `Welcome, <span>${currentUser.username}</span>${currentUser.role === "admin" ? ' <span style="color:var(--accent2);font-size:12px;">[ADMIN]</span>' : ""}`;
    document.getElementById("user-bar-likes").textContent = (currentUser.likes_sent || 0).toLocaleString();
    document.getElementById("user-bar-lobbies").textContent = (currentUser.lobbies_created || 0).toLocaleString();
    loginSection.style.display = "none";
    if (currentUser.role === "admin") showAdminPanel();
  } else {
    navBtn.textContent = "Login";
    userBar.style.display = "none";
    loginSection.style.display = "block";
    const adminSec = document.getElementById("admin-section");
    if (adminSec) adminSec.style.display = "none";
  }
}

/* ─── MODAL ─────────────────────────────────── */
function openModal() {
  document.getElementById("auth-modal").classList.add("active");
}
function closeModal() {
  document.getElementById("auth-modal").classList.remove("active");
  document.getElementById("modal-msg").className = "modal-msg";
  document.getElementById("modal-msg").textContent = "";
}
function switchTab(tab) {
  document.querySelectorAll(".modal-tab").forEach(t => t.classList.remove("active"));
  document.querySelector(`[data-tab="${tab}"]`).classList.add("active");
  document.getElementById("login-form").style.display = tab === "login" ? "flex" : "none";
  document.getElementById("register-form").style.display = tab === "register" ? "flex" : "none";
  document.getElementById("modal-msg").className = "modal-msg";
}

async function doLogin(e) {
  e.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  const msg = document.getElementById("modal-msg");

  if (!username || !password) {
    msg.className = "modal-msg error";
    msg.textContent = "Isi semua field!";
    return;
  }

  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true;
  btn.textContent = "⏳ Login...";

  try {
    const r = await fetch(`${API}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await r.json();
    if (r.ok) {
      saveSession(data.token, data.user);
      closeModal();
      toast(`Welcome back, ${data.user.username}! 🔥`, "success");
    } else {
      msg.className = "modal-msg error";
      msg.textContent = data.error || "Login gagal";
    }
  } catch {
    msg.className = "modal-msg error";
    msg.textContent = "Koneksi error. Coba lagi.";
  } finally {
    btn.disabled = false;
    btn.textContent = "🔐 LOGIN";
  }
}

async function doRegister(e) {
  e.preventDefault();
  const username = document.getElementById("reg-username").value.trim();
  const email = document.getElementById("reg-email").value.trim();
  const password = document.getElementById("reg-password").value;
  const msg = document.getElementById("modal-msg");

  if (!username || !email || !password) {
    msg.className = "modal-msg error";
    msg.textContent = "Isi semua field!";
    return;
  }

  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true;
  btn.textContent = "⏳ Mendaftar...";

  try {
    const r = await fetch(`${API}/api/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password })
    });
    const data = await r.json();
    if (r.ok) {
      saveSession(data.token, data.user);
      closeModal();
      toast(`Akun berhasil dibuat! Welcome, ${data.user.username} 🎮`, "success");
    } else {
      msg.className = "modal-msg error";
      msg.textContent = data.error || "Registrasi gagal";
    }
  } catch {
    msg.className = "modal-msg error";
    msg.textContent = "Koneksi error. Coba lagi.";
  } finally {
    btn.disabled = false;
    btn.textContent = "🚀 DAFTAR SEKARANG";
  }
}

/* ─── TOOLS ─────────────────────────────────── */
function requireLogin() {
  if (!currentUser) {
    toast("Login dulu untuk menggunakan fitur ini!", "error");
    openModal();
    return false;
  }
  return true;
}

function setLoading(btn, loadingText) {
  btn.disabled = true;
  btn._origText = btn.textContent;
  btn.textContent = loadingText;
}
function clearLoading(btn) {
  btn.disabled = false;
  btn.textContent = btn._origText;
}

async function sendLike() {
  if (!requireLogin()) return;
  const uid = document.getElementById("like-uid").value.trim();
  const region = document.getElementById("like-region").value;
  const result = document.getElementById("like-result");
  const btn = document.querySelector(".btn-orange");

  if (!uid) { toast("Masukkan UID Free Fire!", "error"); return; }
  if (!/^\d+$/.test(uid)) { toast("UID harus berupa angka!", "error"); return; }

  setLoading(btn, "⏳ Mengirim...");
  result.className = "tool-result loading";
  result.textContent = "⏳ Menghubungi server Garena... (bisa 15–60 detik)";

  try {
    const r = await fetch(`${API}/api/like`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`
      },
      body: JSON.stringify({ uid, region })
    });
    const data = await r.json();
    if (r.ok && data.success) {
      result.className = "tool-result success";
      const playerInfo = data.player_name ? `<b>${data.player_name}</b> (UID: ${uid})` : `UID <b>${uid}</b>`;
      const likeInfo = data.likes_before > 0
        ? `<br>📊 Before: <b>${data.likes_before.toLocaleString()}</b> → After: <b>${data.likes_after.toLocaleString()}</b>`
        : "";
      const accInfo = data.accounts_used > 0 ? `<br><small style="color:var(--text-dim)">${data.accounts_used} guest account digunakan</small>` : "";
      result.innerHTML = `✅ Like berhasil dikirim ke ${playerInfo}${likeInfo}${accInfo}
        <br><small style="color:var(--text-dim)">Counter like di profil akan update dalam 1–5 menit</small>`;
      toast(`Like dikirim ke ${data.player_name || uid}! ❤️`, "success");
      refreshMe();
      loadProgress();
    } else {
      result.className = "tool-result error";
      result.innerHTML = `❌ ${data.error || data.message || "Gagal mengirim like"}`;
    }
  } catch {
    result.className = "tool-result error";
    result.textContent = "❌ Koneksi error. Coba lagi.";
  } finally {
    clearLoading(btn);
  }
}

async function createLobby() {
  if (!requireLogin()) return;
  const uid = document.getElementById("lobby-uid").value.trim();
  const region = document.getElementById("lobby-region").value;
  const result = document.getElementById("lobby-result");
  const btn = document.querySelector(".btn-blue");

  if (!uid) { toast("Masukkan UID Free Fire!", "error"); return; }
  if (!/^\d+$/.test(uid)) { toast("UID harus berupa angka!", "error"); return; }

  setLoading(btn, "⏳ Membuat...");
  result.className = "tool-result loading";
  result.textContent = "⏳ Membuat Lobby 5 di server Garena...";

  try {
    const r = await fetch(`${API}/api/lobby`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`
      },
      body: JSON.stringify({ uid, region })
    });
    const data = await r.json();
    if (r.ok && data.success) {
      result.className = "tool-result success";
      const accInfo = data.accounts_used > 0
        ? `<br><small style="color:var(--text-dim)">${data.accounts_used} guest account digunakan</small>`
        : "";
      result.innerHTML = `✅ Lobby berhasil dibuat!<br>🔑 Kode: <b style="font-size:20px;letter-spacing:4px;color:#ffd700">${data.lobby_code}</b>${accInfo}`;
      toast(`Lobby dibuat! Kode: ${data.lobby_code} 👥`, "success");
      refreshMe();
    } else {
      result.className = "tool-result error";
      result.textContent = "❌ " + (data.error || "Gagal membuat lobby");
    }
  } catch {
    result.className = "tool-result error";
    result.textContent = "❌ Koneksi error. Coba lagi.";
  } finally {
    clearLoading(btn);
  }
}

/* ─── PROGRESS ──────────────────────────────── */
async function loadProgress() {
  try {
    const r = await fetch(`${API}/api/progress`);
    const data = await r.json();
    renderProgress(data.entries || [], data.source);
  } catch {}
}

function renderProgress(entries, source) {
  const grid = document.getElementById("progress-grid");
  const empty = document.getElementById("progress-empty");

  if (!entries.length) {
    grid.innerHTML = "";
    empty.style.display = "block";
    return;
  }

  empty.style.display = "none";
  grid.innerHTML = "";

  entries.forEach(e => {
    const pct = e.target > 0 ? Math.min(100, Math.round((e.proses / e.target) * 100)) : 0;
    const card = document.createElement("div");
    card.className = "prog-card";
    card.innerHTML = `
      <div class="prog-header">
        <div>
          <div class="prog-name">${e.name}</div>
          <div class="prog-uid">UID: ${e.uid}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <div class="prog-status"></div>
          <button class="prog-share" onclick="shareProgress('${e.uid}','${e.name}')">📤</button>
        </div>
      </div>
      <div class="prog-stats">
        Before: <span>${e.before.toLocaleString()}</span>
        &nbsp;+<span style="color:var(--green)">${e.added.toLocaleString()}</span>&nbsp;
        Total: <span>${e.total.toLocaleString()}</span>
      </div>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" style="width:${pct}%"></div>
      </div>
      <div class="prog-footer">
        <span>⏳ ${e.proses.toLocaleString()} / ${e.target.toLocaleString()} Like</span>
        <span>Tersisa: ${e.tersisa.toLocaleString()}</span>
      </div>
    `;
    grid.appendChild(card);
  });
}

function shareProgress(uid, name) {
  const text = `🔥 ${name} sedang GB Like di Kios Gamer!\nUID: ${uid}\n\nCek di: ${location.href}`;
  if (navigator.share) {
    navigator.share({ text, url: location.href });
  } else {
    navigator.clipboard.writeText(text).then(() => toast("Progress disalin ke clipboard! 📋", "info"));
  }
}

function loadStats() {
  fetch(`${API}/api/stats`).then(r => r.json()).then(data => {
    const el = document.getElementById("stats-bar");
    if (el) {
      el.innerHTML = `
        👥 <b>${data.total_users}</b> Users &nbsp;|&nbsp;
        ❤ <b>${data.total_likes}</b> Orders Like &nbsp;|&nbsp;
        🎮 <b>${data.total_lobbies}</b> Lobbies
      `;
    }
  }).catch(() => {});
}

/* ─── ADMIN PANEL ───────────────────────────── */
function showAdminPanel() {
  if (!currentUser || currentUser.role !== "admin") return;
  document.getElementById("admin-section").style.display = "block";
  loadAccountStats();
}

async function loadAccountStats() {
  try {
    const r = await fetch(`${API}/api/admin/accounts`, {
      headers: { Authorization: `Bearer ${getToken()}` }
    });
    if (!r.ok) return;
    const data = await r.json();
    const el = document.getElementById("account-stats");
    if (!el) return;
    el.innerHTML = Object.entries(data.accounts).map(([reg, count]) =>
      `<div class="acc-stat"><span class="acc-reg">${reg}</span><span class="acc-count ${count > 0 ? 'has-acc' : ''}">${count} akun</span></div>`
    ).join("");
  } catch {}
}

async function adminAddAccount(e) {
  e.preventDefault();
  const region   = document.getElementById("admin-region").value;
  const uid      = document.getElementById("admin-uid").value.trim();
  const password = document.getElementById("admin-pass").value.trim();
  const result   = document.getElementById("admin-result");

  if (!uid || !password) { toast("Isi UID dan password!", "error"); return; }

  result.style.display = "block";
  result.className = "tool-result loading";
  result.textContent = "⏳ Menambahkan akun...";

  try {
    const r = await fetch(`${API}/api/admin/add-account`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ region, uid, password })
    });
    const data = await r.json();
    result.className = r.ok ? "tool-result success" : "tool-result error";
    result.textContent = (r.ok ? "✅ " : "❌ ") + (data.message || data.error);
    if (r.ok) { loadAccountStats(); toast(data.message, "success"); }
  } catch {
    result.className = "tool-result error";
    result.textContent = "❌ Koneksi error";
  }
}

async function adminAutoGenerate() {
  const region = document.getElementById("gen-region").value;
  const count  = parseInt(document.getElementById("gen-count").value) || 5;
  const result = document.getElementById("admin-result");

  result.style.display = "block";
  result.className = "tool-result loading";
  result.textContent = `⏳ Generating ${count} guest account untuk ${region}... (background)`;

  try {
    const r = await fetch(`${API}/api/admin/auto-generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ region, count })
    });
    const data = await r.json();
    result.className = "tool-result success";
    result.textContent = "✅ " + data.message;
    toast(data.message, "info");
    setTimeout(loadAccountStats, 30000);
  } catch {
    result.className = "tool-result error";
    result.textContent = "❌ Koneksi error";
  }
}

async function adminMakeAdmin(e) {
  e.preventDefault();
  const username = document.getElementById("make-admin-username").value.trim();
  const result   = document.getElementById("admin-result");

  if (!username) { toast("Isi username target!", "error"); return; }

  result.style.display = "block";
  result.className = "tool-result loading";
  result.textContent = "⏳ Memproses...";

  try {
    const r = await fetch(`${API}/api/admin/make-admin`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ username })
    });
    const data = await r.json();
    result.className = r.ok ? "tool-result success" : "tool-result error";
    result.textContent = (r.ok ? "✅ " : "❌ ") + (data.message || data.error);
  } catch {
    result.className = "tool-result error";
    result.textContent = "❌ Koneksi error";
  }
}

/* ─── INIT ───────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  initParticles();
  loadSession();
  loadProgress();
  loadStats();

  progressInterval = setInterval(loadProgress, 15000);

  document.getElementById("nav-user-btn").addEventListener("click", openModal);
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("auth-modal").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });

  document.querySelectorAll(".modal-tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  document.getElementById("login-form").addEventListener("submit", doLogin);
  document.getElementById("register-form").addEventListener("submit", doRegister);

  document.getElementById("btn-logout").addEventListener("click", logout);
  document.getElementById("btn-nav-login").addEventListener("click", openModal);
});
