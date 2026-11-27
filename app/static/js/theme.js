(() => {
  // use the saved theme or the device preference
  const savedTheme = (() => {
    try {
      return localStorage.getItem("hireboard-theme");
    } catch {
      return null;
    }
  })();
  const darkPreference = window.matchMedia("(prefers-color-scheme: dark)");
  const page = document.documentElement;
  let theme = savedTheme === "light" || savedTheme === "dark"
    ? savedTheme
    : (darkPreference.matches ? "dark" : "light");
  page.dataset.bsTheme = theme;

  // update the theme button and remember the choice
  window.addEventListener("DOMContentLoaded", () => {
    const buttons = document.querySelectorAll("[data-theme-toggle]");
    function updateButtons() {
      buttons.forEach(button => {
        button.textContent = theme === "dark" ? "light mode" : "dark mode";
        button.setAttribute("aria-label", "switch to " + button.textContent);
      });
    }
    updateButtons();
    buttons.forEach(button => {
      button.addEventListener("click", () => {
        theme = theme === "dark" ? "light" : "dark";
        page.dataset.bsTheme = theme;
        try {
          localStorage.setItem("hireboard-theme", theme);
        } catch {
          // theme still works without storage
        }
        updateButtons();
      });
    });
  });
})();
