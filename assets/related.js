/* Related-tools entrance, mirroring rating-widget.js.
 *
 * The section is "armed" here, never in the HTML, so a reader without JS sees
 * the block fully visible. Once armed, an IntersectionObserver reveals it as it
 * scrolls in; the cards stagger off their `--i` index in CSS.
 *
 * Hiding content until it is scrolled to is only safe when something always
 * un-hides it, so three independent paths lead back to visible:
 *   1. the observer fires as the section enters the viewport;
 *   2. a one-off scroll listener catches the case where it never fires;
 *   3. a short timer reveals any section already on screen.
 * On top of that the `tf-armed` class is dropped once the entrance is over, so
 * even an engine that stalls the CSS transition falls back to the stylesheet's
 * default, fully-opaque state. */
(function () {
  "use strict";

  var REVEAL_MS = 1400;

  function all() {
    return document.querySelectorAll(".tf-related");
  }

  function reduceMotion() {
    return (
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function reveal(node) {
    if (node.classList.contains("tf-in")) return;
    node.classList.add("tf-in");
    // Drop the hiding rule once the entrance is over, and stop transitioning at
    // the same time. If the transition ran, the block is already opaque and
    // nothing changes; if it did not (an engine that stalls animations), opacity
    // snaps to its default and the block is visible either way.
    window.setTimeout(function () {
      node.classList.add("tf-done");
      node.classList.remove("tf-armed");
    }, REVEAL_MS);
  }

  function onScreen(node) {
    var r = node.getBoundingClientRect();
    return r.top < window.innerHeight && r.bottom > 0;
  }

  function arm() {
    var nodes = all();
    if (!nodes.length) return;

    if (reduceMotion() || !("IntersectionObserver" in window)) {
      // Nothing to animate, or nothing to animate it with: show it now.
      for (var i = 0; i < nodes.length; i++) nodes[i].classList.add("tf-in");
      return;
    }

    for (var j = 0; j < nodes.length; j++) nodes[j].classList.add("tf-armed");

    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          reveal(entry.target);
          io.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.05 }
    );

    for (var k = 0; k < nodes.length; k++) io.observe(nodes[k]);

    window.addEventListener(
      "scroll",
      function () {
        var list = all();
        for (var m = 0; m < list.length; m++) {
          // Only what is actually on screen, so a section further down still
          // gets its entrance when the reader reaches it.
          if (onScreen(list[m])) reveal(list[m]);
        }
      },
      { passive: true }
    );

    // Fast path: anything already on screen that the observer missed.
    window.setTimeout(function () {
      var list = all();
      for (var n = 0; n < list.length; n++) {
        if (onScreen(list[n])) reveal(list[n]);
      }
    }, 1500);

    // Long stop: if the block is somehow still armed after this, show it
    // regardless of position. Losing one entrance animation is always better
    // than leaving a section permanently invisible.
    window.setTimeout(function () {
      var list = all();
      for (var p = 0; p < list.length; p++) reveal(list[p]);
    }, 6000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arm);
  } else {
    arm();
  }
})();
