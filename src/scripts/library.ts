// Library search / tag filter / sort / pagination over server-rendered cards.

type Item = {
  el: HTMLElement;
  title: string;
  date: string;
  time: number;
  seconds: number;
  tags: string[];
};

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function parseLocalDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function init(root: HTMLElement): void {
  const source = root.querySelector<HTMLElement>("[data-library-source]");
  const results = root.querySelector<HTMLElement>("[data-library-results]");
  const controls = root.querySelector<HTMLElement>("[data-library-controls]");
  const countEl = root.querySelector<HTMLElement>("[data-library-count]");
  const search = root.querySelector<HTMLInputElement>("#librarySearch");
  const tagSel = root.querySelector<HTMLSelectElement>("#libraryTag");
  const sortSel = root.querySelector<HTMLSelectElement>("#librarySort");
  const orderSel = root.querySelector<HTMLSelectElement>("#libraryOrder");
  if (!source || !results || !controls || !countEl || !search || !tagSel || !sortSel || !orderSel) return;

  const pageSize = Number(root.dataset.pageSize || 24);

  const items: Item[] = Array.from(source.querySelectorAll<HTMLElement>(".library-item")).map((el) => {
    const date = el.dataset.date || "";
    const d = parseLocalDate(date);
    return {
      el,
      title: el.dataset.title || "",
      date,
      time: Number.isNaN(d.getTime()) ? 0 : d.getTime(),
      seconds: Number(el.dataset.seconds || 0),
      tags: (el.dataset.tags || "").split("|").filter(Boolean),
    };
  });

  // Tag badges inside cards switch the filter instead of navigating.
  items.forEach((it) =>
    it.el.querySelectorAll<HTMLAnchorElement>("[data-tag]").forEach((a) =>
      a.addEventListener("click", (e) => {
        e.preventDefault();
        tagSel.value = a.dataset.tag || "";
        page = 1;
        render();
        syncUrl();
      }),
    ),
  );

  const initialTag = new URLSearchParams(location.search).get("tag");
  if (initialTag && Array.from(tagSel.options).some((o) => o.value === initialTag)) {
    tagSel.value = initialTag;
  }

  source.classList.add("is-hidden");
  controls.hidden = false;
  countEl.hidden = false;

  let page = 1;

  const syncUrl = () => {
    const url = new URL(location.href);
    if (tagSel.value) url.searchParams.set("tag", tagSel.value);
    else url.searchParams.delete("tag");
    history.replaceState(null, "", url);
  };

  const filtered = (): Item[] => {
    const term = search.value.trim().toLowerCase();
    const tag = tagSel.value;
    const mult = orderSel.value === "asc" ? 1 : -1;
    const field = sortSel.value;
    const out = items.filter((it) => {
      const matchesSearch =
        !term ||
        it.title.toLowerCase().includes(term) ||
        it.date.includes(term) ||
        it.tags.join(" ").toLowerCase().includes(term);
      const matchesTag = !tag || it.tags.includes(tag);
      return matchesSearch && matchesTag;
    });
    out.sort((a, b) => {
      if (field === "name") return a.title.localeCompare(b.title) * mult;
      if (field === "length") return (a.seconds - b.seconds) * mult;
      return (a.time - b.time) * mult;
    });
    return out;
  };

  const button = (label: string, target: number, active = false, disabled = false) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.disabled = disabled;
    if (active) b.classList.add("is-active");
    b.addEventListener("click", () => {
      page = target;
      render();
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return b;
  };

  const pagination = (total: number): HTMLElement | null => {
    const pages = Math.max(1, Math.ceil(total / pageSize));
    if (pages <= 1) return null;
    const wrap = document.createElement("div");
    wrap.className = "library-pagination";
    wrap.appendChild(button("Prev", Math.max(1, page - 1), false, page === 1));

    const show = new Set<number>([1, 2, pages - 1, pages, page - 1, page, page + 1]);
    const list = [...show].filter((p) => p >= 1 && p <= pages).sort((a, b) => a - b);
    let last = 0;
    for (const p of pages <= 7 ? Array.from({ length: pages }, (_, i) => i + 1) : list) {
      if (last && p - last > 1) {
        const dots = document.createElement("span");
        dots.className = "pagination-ellipsis";
        dots.textContent = "...";
        wrap.appendChild(dots);
      }
      wrap.appendChild(button(String(p), p, p === page));
      last = p;
    }
    wrap.appendChild(button("Next", Math.min(pages, page + 1), false, page === pages));
    return wrap;
  };

  const render = () => {
    const list = filtered();
    const pages = Math.max(1, Math.ceil(list.length / pageSize));
    if (page > pages) page = pages;
    const slice = list.slice((page - 1) * pageSize, page * pageSize);

    countEl.textContent = `${list.length} sermon${list.length === 1 ? "" : "s"} shown  |  Page ${page} of ${pages}`;
    results.replaceChildren();

    if (sortSel.value === "date") {
      let year = "";
      let month = "";
      let row: HTMLElement | null = null;
      for (const it of slice) {
        const d = parseLocalDate(it.date);
        const y = it.time ? String(d.getFullYear()) : it.date.slice(0, 4) || "Unknown Year";
        const m = it.time ? MONTHS[d.getMonth()] : "Unknown Month";
        if (y !== year) {
          year = y;
          month = "";
          const h = document.createElement("h2");
          h.textContent = y;
          results.appendChild(h);
        }
        if (m !== month) {
          month = m;
          const h = document.createElement("h3");
          h.textContent = m;
          results.appendChild(h);
          row = document.createElement("div");
          row.className = "library-month-row library-results-group";
          results.appendChild(row);
        }
        row!.appendChild(it.el);
      }
    } else {
      const row = document.createElement("div");
      row.className = "library-flat-row library-results-group";
      slice.forEach((it) => row.appendChild(it.el));
      results.appendChild(row);
    }

    const pager = pagination(list.length);
    if (pager) results.appendChild(pager);
  };

  let timer: number | undefined;
  const debounced = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      page = 1;
      render();
      syncUrl();
    }, 200);
  };
  [tagSel, sortSel, orderSel].forEach((el) => el.addEventListener("change", debounced));
  search.addEventListener("input", debounced);

  render();
}

const root = document.querySelector<HTMLElement>("[data-library]");
if (root) init(root);
