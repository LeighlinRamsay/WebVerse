(() => {
  // Tiny UX polish only. No dependencies.
  const q = (sel) => document.querySelector(sel);

  // Auto-focus first input on forms
  const firstInput = q("form .field input");
  if (firstInput) {
    try { firstInput.focus(); } catch (_) {}
  }

  // Make cards feel clickable where appropriate
  document.querySelectorAll("[data-href]").forEach(el => {
    el.style.cursor = "pointer";
    el.addEventListener("click", (e) => {
      const a = e.target.closest("a");
      if (a) return;
      const href = el.getAttribute("data-href");
      if (href) window.location.href = href;
    });
  });
})();
