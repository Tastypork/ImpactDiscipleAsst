// Shared page behaviour: navbar toggle, sticky nav, back-to-top, carousels.

function initNav(): void {
  const toggle = document.querySelector<HTMLButtonElement>("[data-nav-toggle]");
  const panel = document.getElementById("navbarCollapse");
  if (!toggle || !panel) return;
  toggle.addEventListener("click", () => {
    const open = panel.classList.toggle("show");
    toggle.setAttribute("aria-expanded", String(open));
  });
  panel.querySelectorAll("a.nav-link").forEach((a) =>
    a.addEventListener("click", () => {
      panel.classList.remove("show");
      toggle.setAttribute("aria-expanded", "false");
    }),
  );
}

function initScrollEffects(): void {
  const navBar = document.querySelector(".nav-bar");
  const backToTop = document.querySelector<HTMLAnchorElement>(".back-to-top");
  const update = () => {
    const y = window.scrollY;
    navBar?.classList.toggle("nav-sticky", y > 150);
    backToTop?.classList.toggle("is-visible", y > 100);
  };
  window.addEventListener("scroll", update, { passive: true });
  update();
  backToTop?.addEventListener("click", (e) => {
    e.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function initCarousel(root: HTMLElement): void {
  const track = root.querySelector<HTMLElement>("[data-carousel-track]");
  const prev = root.querySelector<HTMLButtonElement>("[data-carousel-prev]");
  const next = root.querySelector<HTMLButtonElement>("[data-carousel-next]");
  if (!track || !prev || !next) return;

  const loop = root.dataset.loop === "true";
  const autoplayMs = Number(root.dataset.autoplay || 0);

  const slideWidth = () => {
    const first = track.firstElementChild as HTMLElement | null;
    if (!first) return track.clientWidth;
    const gap = parseFloat(getComputedStyle(track).columnGap || "0") || 0;
    return first.getBoundingClientRect().width + gap;
  };
  const maxScroll = () => track.scrollWidth - track.clientWidth;
  const atStart = () => track.scrollLeft <= 1;
  const atEnd = () => track.scrollLeft >= maxScroll() - 1;

  const updateButtons = () => {
    if (loop) return;
    prev.disabled = atStart();
    next.disabled = atEnd();
  };

  const go = (dir: 1 | -1) => {
    if (loop && dir === 1 && atEnd()) {
      track.scrollTo({ left: 0 });
      return;
    }
    if (loop && dir === -1 && atStart()) {
      track.scrollTo({ left: maxScroll() });
      return;
    }
    track.scrollBy({ left: dir * slideWidth() });
  };

  prev.addEventListener("click", () => go(-1));
  next.addEventListener("click", () => go(1));
  track.addEventListener("scroll", updateButtons, { passive: true });
  window.addEventListener("resize", updateButtons);
  updateButtons();

  if (autoplayMs > 0) {
    let timer: number | undefined;
    const start = () => {
      stop();
      timer = window.setInterval(() => go(1), autoplayMs);
    };
    const stop = () => {
      if (timer) window.clearInterval(timer);
      timer = undefined;
    };
    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", start);
    root.addEventListener("focusin", stop);
    root.addEventListener("focusout", start);
    document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
    start();
  }
}

initNav();
initScrollEffects();
document.querySelectorAll<HTMLElement>("[data-carousel]").forEach(initCarousel);
