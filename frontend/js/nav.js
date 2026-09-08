document.addEventListener("DOMContentLoaded", () => {
  const burger = document.getElementById("nav-burger");
  const nav = document.getElementById("site-nav");
  if (burger && nav) {
    burger.addEventListener("click", () => nav.classList.toggle("nav-open"));
  }

  // The header is transparent by default so it can overlay a hero image.
  // Pages without a hero need it solid immediately; the home page (with a
  // hero) only needs it solid once scrolled past that hero.
  const header = document.getElementById("site-header");
  if (!header) return;
  const hero = document.querySelector(".hero");

  if (!hero) {
    header.classList.add("scrolled");
    return;
  }

  const applyScrollState = () => {
    header.classList.toggle("scrolled", window.scrollY > hero.offsetHeight - 100);
  };
  applyScrollState();
  window.addEventListener("scroll", applyScrollState, { passive: true });
});
