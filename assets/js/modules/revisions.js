/**
 * Revision-screenshot accordion (About page).
 *
 * The gallery is a fluid flexbox accordion (after Simey's "Stripe Sessions"
 * carousel): all strips are always visible, the active one flex-expands.
 * State lives in a radio group — one visually-hidden radio per strip — so
 * click-to-expand works without JS via the labels. This module only adds the
 * arrows + slide counter (server-rendered hidden) and keyboard support; CSS
 * (":has" + ":checked") does all the visual work, so JS never touches styles.
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

  prev.hidden = false;
  next.hidden = false;
  counter.hidden = false;
  update();
}