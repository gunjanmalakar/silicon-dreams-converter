// Runs in <head> to apply the saved theme before first paint (no flash).
try { var t = localStorage.getItem("sd-theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) {}
