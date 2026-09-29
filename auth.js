const THEME_KEY = "sonarr-nyaa-proxy-manager.theme";
const form = document.querySelector("#loginForm");
const error = document.querySelector("#loginError");
const button = document.querySelector("#loginButton");
const themeToggle = document.querySelector("#themeToggle");
const themeLabel = document.querySelector("#themeLabel");
let currentTheme = localStorage.getItem(THEME_KEY) || "dark";

function setTheme(theme) {
  currentTheme = theme;
  document.documentElement.dataset.theme = theme;
  themeLabel.textContent = theme === "dark" ? "Light" : "Dark";
  themeToggle.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`);
  localStorage.setItem(THEME_KEY, theme);
}

themeToggle.addEventListener("click", () => setTheme(currentTheme === "dark" ? "light" : "dark"));

form.addEventListener("submit", async event => {
  event.preventDefault();
  error.hidden = true;
  button.disabled = true;
  button.textContent = "Signing in...";
  const formData = new FormData(form);
  try {
    const response = await fetch("/manager/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: formData.get("username"), password: formData.get("password") }),
    });
    if (response.ok) {
      window.location.replace("/manager/");
      return;
    }
    const payload = await response.json().catch(() => ({}));
    error.textContent = response.status === 401 ? "Invalid username or password." : (payload.error || "Sign-in is unavailable.");
    error.hidden = false;
  } catch {
    error.textContent = "Could not reach the manager. Please try again.";
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Sign in";
  }
});

setTheme(currentTheme);
