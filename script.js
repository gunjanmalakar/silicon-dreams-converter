(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const root = document.documentElement;

  // Theme toggle
  const toggle = $("#themeToggle");
  if (toggle) toggle.addEventListener("click", () => {
    const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("sd-theme", next); } catch (e) {}
  });

  document.querySelectorAll("[data-year]").forEach(el => (el.textContent = new Date().getFullYear()));

  const form = $("#convertForm");
  if (!form) return;

  const urlInput = $("#videoUrl"), fetchBtn = $("#fetchBtn"), errorBox = $("#error");
  const result = $("#result"), qualitySel = $("#quality"), convertBtn = $("#convertBtn");
  const progress = $("#progress"), bar = $("#bar"), pText = $("#progressText"), pPct = $("#progressPct");
  const API = window.SD_API_BASE ? String(window.SD_API_BASE).replace(/\/+$/, "") + "/" : "";
  const VALID = /^(https?:\/\/)?((www|m|web|music)\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com|facebook\.com|fb\.watch|fb\.com)\/\S+/i;
  let currentUrl = "";

  const showError = msg => { errorBox.textContent = msg; errorBox.hidden = !msg; };
  const fmtTime = s => {
    if (!s && s !== 0) return "";
    s = Math.round(s);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(sec).padStart(2, "0");
  };
  const fmtBytes = b => b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB";
  const busy = (btn, on, label) => {
    btn.disabled = on;
    btn.innerHTML = on ? '<span class="spinner" aria-hidden="true"></span>' + label : btn.dataset.label;
  };
  [fetchBtn, convertBtn].forEach(b => (b.dataset.label = b.innerHTML));

  // Paste from clipboard
  const pasteBtn = $("#pasteBtn");
  if (pasteBtn) {
    if (!navigator.clipboard || !navigator.clipboard.readText) pasteBtn.hidden = true;
    pasteBtn.addEventListener("click", async () => {
      try { urlInput.value = (await navigator.clipboard.readText()).trim(); urlInput.focus(); } catch (e) {}
    });
  }

  // Step 1 — fetch video details
  form.addEventListener("submit", async e => {
    e.preventDefault();
    showError("");
    const url = urlInput.value.trim();
    if (!VALID.test(url)) { showError("Please paste a valid YouTube or Facebook video link."); urlInput.focus(); return; }
    busy(fetchBtn, true, "Fetching…");
    result.hidden = true;
    try {
      const res = await fetch(API + "api/info", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url })
      });
      const data = await res.json().catch(() => null);
      if (!data) throw new Error("The converter service isn't reachable right now (error " + res.status + "). Please try again later.");
      if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
      currentUrl = url;
      renderPreview(data);
    } catch (err) {
      showError(err.message || "Network error. Please check your connection.");
    } finally {
      busy(fetchBtn, false);
    }
  });

  function renderPreview(d) {
    $("#thumb").src = d.thumbnail || "logo.svg";
    $("#thumb").alt = d.title ? "Thumbnail: " + d.title : "Video thumbnail";
    $("#duration").textContent = fmtTime(d.duration);
    $("#duration").hidden = !d.duration;
    $("#platform").textContent = d.platform || "Video";
    $("#title").textContent = d.title || "Untitled video";
    $("#uploader").textContent = d.uploader ? "by " + d.uploader : "";

    qualitySel.innerHTML = '<option value="best">Best available</option>';
    (d.heights || []).forEach(h => {
      const label = h >= 2160 ? "4K (2160p)" : h >= 1440 ? "2K (1440p)" : h + "p" + (h >= 720 ? " HD" : "");
      qualitySel.insertAdjacentHTML("beforeend", `<option value="${h}">${label}</option>`);
    });
    if (!(d.heights || []).length)
      ["1080", "720", "480", "360"].forEach(h => qualitySel.insertAdjacentHTML("beforeend", `<option value="${h}">${h}p</option>`));

    progress.hidden = true;
    result.hidden = false;
    syncQuality();
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const selectedFormat = () => (form.querySelector('input[name="format"]:checked') || {}).value || "mp4";
  const AUDIO = ["mp3", "m4a", "wav"];
  function syncQuality() { qualitySel.disabled = AUDIO.includes(selectedFormat()); }
  form.querySelectorAll('input[name="format"]').forEach(r => r.addEventListener("change", syncQuality));

  // Step 2 — convert and download
  convertBtn.addEventListener("click", async () => {
    if (!currentUrl) return;
    showError("");
    const fmt = selectedFormat();
    const q = AUDIO.includes(fmt) ? "best" : qualitySel.value;
    const qs = new URLSearchParams({ url: currentUrl, format: fmt, quality: q });

    busy(convertBtn, true, "Converting…");
    progress.hidden = false;
    bar.classList.add("indeterminate");
    bar.firstElementChild.style.width = "";
    pText.textContent = "Converting on our servers — this can take a minute for long videos…";
    pPct.textContent = "";

    try {
      const res = await fetch(API + "api/download?" + qs.toString());
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data && data.error ? data.error : "The converter service isn't reachable right now (error " + res.status + "). Please try again later.");
      }
      const total = +res.headers.get("Content-Length") || 0;
      const name = fileName(res.headers.get("Content-Disposition")) || "video." + fmt;
      let blob;
      if (res.body && res.body.getReader) {
        const reader = res.body.getReader(), chunks = [];
        let got = 0;
        bar.classList.remove("indeterminate");
        pText.textContent = "Downloading " + name;
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value); got += value.length;
          if (total) { const p = Math.round((got / total) * 100); bar.firstElementChild.style.width = p + "%"; pPct.textContent = p + "%"; }
          else pPct.textContent = fmtBytes(got);
        }
        blob = new Blob(chunks, { type: res.headers.get("Content-Type") || "application/octet-stream" });
      } else {
        blob = await res.blob();
      }
      const href = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), { href, download: name });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(href), 60000);

      bar.classList.remove("indeterminate");
      bar.firstElementChild.style.width = "100%";
      pText.innerHTML = '<span class="success">✓ Done!</span> Your ' + fmt.toUpperCase() + " file has been saved.";
      pPct.textContent = fmtBytes(blob.size);
    } catch (err) {
      progress.hidden = true;
      showError(err.message || "Network error. Please try again.");
    } finally {
      busy(convertBtn, false);
    }
  });

  function fileName(cd) {
    if (!cd) return "";
    const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    if (star) try { return decodeURIComponent(star[1]); } catch (e) {}
    const plain = /filename="?([^";]+)"?/i.exec(cd);
    return plain ? plain[1] : "";
  }
})();
