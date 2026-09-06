/**
 * Revision-screenshot accordion (About page).
 *
 * The gallery is a fluid flexbox accordion (after Simey's "Stripe Sessions"
 * carousel): all strips are always visible, the active one flex-expands.
 * State lives in a radio group — one visually-hidden radio per strip — so
 * click-to-expand works without JS via the labels. This module adds the
 * arrows + slide counter (server-rendered hidden), keyboard support, and a
 * screenshot lightbox: clicking an already-selected strip pops the image up
 * in a native <dialog> (any click inside or on the backdrop closes it).
 * CSS (":has" + ":checked") does all the visual work, so JS never touches
 * styles.
 */

export function init(doc = document) {
  const section = doc.querySelector("[data-rev-accordion]");
  if (!section) return;

  const radios = Array.from(
    section.querySelectorAll('input[type="radio"][name="rev-history"]')
  );
  if (radios.length < 2) return;

  const prev = section.querySelector("[data-rev-prev]");
  const next = section.querySelector("[data-rev-next]");
  const counter = section.querySelector("[data-rev-counter]");
  if (!prev || !next || !counter) return;

  const current = () => radios.findIndex((radio) => radio.checked);

  const update = () => {
    const index = current();
    if (index === -1) return;
    counter.textContent = `${index + 1} / ${radios.length}`;
  };

  const step = (delta) => {
    const index = (current() + delta + radios.length) % radios.length;
    radios[index].checked = true;
    update();
  };

  prev.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));

  // Radio 'change' fires on native label clicks; JS-driven steps call
  // update() directly (programmatic .checked does not fire 'change').
  radios.forEach((radio) => radio.addEventListener("change", update));

  // Left/Right on the list; the radios' own arrow-key navigation already
  // handles focus on the hidden inputs.
  section.addEventListener("keydown", (event) => {
    if (event.target instanceof HTMLInputElement) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      step(1);
    }
  });

  // Lightbox: clicking an already-selected strip pops the screenshot up
  // large in a native <dialog>; any click inside (or on the ::backdrop)
  // closes it, Esc is native. Without JS the carousel keeps working.
  const lightbox = section.querySelector("[data-rev-lightbox]");
  const lightboxImg = lightbox && lightbox.querySelector("[data-rev-lightbox-img]");
  const lightboxCaption = lightbox && lightbox.querySelector("[data-rev-lightbox-caption]");
  if (lightbox && lightboxImg && typeof lightbox.showModal === "function") {
    section.addEventListener("click", (event) => {
      // The label forwards a second click to the hidden radio, which by
      // then reports checked — that synthetic event must not pop up.
      if (event.target instanceof HTMLInputElement) return;
      const item = event.target.closest(".rev-accordion__item");
      if (!item) return;
      const radio = item.querySelector('input[name="rev-history"]');
      if (!radio || !radio.checked) return; // collapsed strip: select it
      const img = item.querySelector("img");
      if (!img) return;
      const caption = item.querySelector(".rev-accordion__caption");
      lightboxImg.src = img.currentSrc || img.src;
      lightboxImg.alt = img.alt;
      if (lightboxCaption && caption) {
        lightboxCaption.textContent = caption.textContent;
      }
      lightbox.showModal();
    });

    // Clicks on the ::backdrop surface as clicks on the <dialog> itself.
    lightbox.addEventListener("click", () => lightbox.close());
  }

  prev.hidden = false;
  next.hidden = false;
  counter.hidden = false;
  update();
}