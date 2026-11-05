/* ToolGuest rating widget.
 *
 * One script, self-mounting. Add
 *   <script src="/assets/rating-widget.js" defer></script>
 * to any page and the widget appears above the footer.
 *
 * A rating is stored twice: on the server (so every visitor sees the same
 * average) and in localStorage (so a visitor can change their own rating and
 * the widget remembers it). No structured data is emitted, so this carries no
 * review-snippet risk.
 *
 * A score stays editable for a while after it is first given. Inside that
 * window a tap edits the score — the aggregate average moves, the rating count
 * does not. After the window the same visitor's next tap is a fresh review, so
 * both the average and the count move. The server owns that decision; the
 * widget mirrors it so the copy can say which one is about to happen.
 */
(function () {
  "use strict";

  var API = "/api/ratings";
  var STORE_KEY = "tg:rating:";
  var STARS = 5;
  var EDIT_WINDOW_MS = 24 * 60 * 60 * 1000;

  function toolId() {
    var p = location.pathname.replace(/\.html$/, "").replace(/^\/+|\/+$/g, "");
    // The homepage is "/" on the live site but "/index.html" when opened from
    // disk, and both must land on the same key.
    if (!p || p === "index") return "home";
    return p;
  }

  // One line of copy per tool, shown where the plain instruction used to sit.
  // The quote is the welcome, not the instructions.
  var QUOTES = {
    "ai-humanizer": "Wrote it with AI? Let's make it sound like you did.",
    "aspect-ratio-calculator": "Perfect proportions, every single time.",
    "base64-encoder": "Every byte, translated without a word lost.",
    "case-converter": "Little letters, big difference.",
    "color-palette-generator": "Colour is a language. Let's speak it well.",
    "creator-calculator": "Know your worth, down to the last penny.",
    "diff-checker": "Two versions, one clear answer.",
    "font-changer": "The right typeface changes everything.",
    "hash-generator": "One input, one unforgeable fingerprint.",
    "heic-to-jpg": "From Apple's format to everyone's.",
    "image-resizer": "Same picture, perfect size.",
    "invoice-generator": "Get paid, and look professional doing it.",
    "json-formatter": "Messy data, neatly dressed.",
    "lorem-ipsum": "Words that mean nothing, beautifully.",
    "markdown-to-html": "Write simply, publish properly.",
    "meta-tag-preview": "See your link the way Google does.",
    "password-checker": "A strong password is a quiet superpower.",
    "qr-generator": "One small square, endless destinations.",
    "shorts-hooks": "Three seconds to win them over.",
    "thumbnail-downloader": "Grab the frame that sells the video.",
    "url-slug-generator": "Clean links, happy readers.",
    "video-to-blog": "One video, a thousand words.",
    "word-counter": "Every word, accounted for.",
    "youtube-timestamp": "Jump to the exact moment, every time.",
    "youtube-transcript": "Every word of the video, written down.",
    "home": "Twenty-six tools. One tap to say thanks."
  };

  function quoteFor(id) {
    return QUOTES[id] || "Glad you stopped by. Care to rate us?";
  }

  // A thank-you that matches the score. Each score has several lines and one is
  // picked at random, so two visitors who both give five stars rarely see the
  // same words. A one-star reply is warm and curious, not defensive; a five-star
  // reply is the one that should leave the visitor smiling.
  var THANKS = {
    1: [
      "Thanks for the honest one star — tell us what to fix and we will.",
      "Noted, one star. We would love to know what fell short.",
      "One star it is — thanks for telling us straight. We will do better.",
      "Thanks for the nudge. One star is a clear signal and we are listening."
    ],
    2: [
      "Two stars — thanks. That tells us exactly where to improve.",
      "Thanks for the two stars. We are already working on the rest.",
      "Two stars noted — cheers for the honesty.",
      "Appreciated. Two stars today, we will aim higher next time."
    ],
    3: [
      "Three stars — solid. Thanks for taking a second to rate.",
      "Thanks for the three stars. Good is fine, we would love great.",
      "Three stars noted — thanks for the feedback.",
      "Three stars, cheers. Tell us what would make it a five."
    ],
    4: [
      "Four stars — that means a lot. Thank you!",
      "Thanks for four stars. Glad it did the job for you.",
      "Four stars, brilliant — thanks for the kind word.",
      "Four stars. Lovely. Thanks for rating us."
    ],
    5: [
      "Five stars — you have made our day. Thank you!",
      "Wow, five stars! You are a legend — thanks a ton.",
      "Five stars. Cheers! Ratings like this keep ToolGuest free.",
      "Five stars — that is the kind of review that makes our week.",
      "Perfect five. Thank you for the boost — enjoy the tool!"
    ]
  };

  function thanksFor(value) {
    var pool = THANKS[value] || THANKS[5];
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function withinWindow(at) {
    return typeof at === "number" && Date.now() - at < EDIT_WINDOW_MS;
  }

  // The stored value is { s: stars, t: when first rated }. Older builds wrote a
  // bare number, so that shape is still read and treated as just-rated.
  function readLocal(id) {
    try {
      var raw = localStorage.getItem(STORE_KEY + id);
      if (!raw) return null;
      if (raw.charAt(0) === "{") {
        var o = JSON.parse(raw);
        var s = parseInt(o.s, 10);
        if (!(s >= 1 && s <= STARS)) return null;
        var t = Number(o.t);
        return { stars: s, at: Number.isFinite(t) ? t : Date.now() };
      }
      var v = parseInt(raw, 10);
      return v >= 1 && v <= STARS ? { stars: v, at: Date.now() } : null;
    } catch (e) {
      return null;
    }
  }

  function writeLocal(id, stars, at) {
    try {
      localStorage.setItem(STORE_KEY + id, JSON.stringify({ s: stars, t: at }));
    } catch (e) {
      /* private mode — the server copy still holds the rating */
    }
  }

  function api(method, body) {
    var init = { method: method, headers: { Accept: "application/json" } };
    if (body) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    return fetch(API, init).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  var STAR_PATH =
    "M12 2.4l2.92 5.92 6.53.95-4.73 4.6 1.12 6.5L12 17.3l-5.84 3.07 1.12-6.5-4.73-4.6 6.53-.95z";

  function starButton(n) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "tgr__star";
    b.setAttribute("aria-label", n + " star" + (n === 1 ? "" : "s"));
    b.dataset.value = String(n);
    b.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + STAR_PATH + '"/></svg>';
    return b;
  }

  function confetti(host) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var colours = ["#fbbf24", "#7c7cff", "#34d399", "#f472b6", "#60a5fa"];
    var i;
    for (i = 0; i < 16; i++) {
      var bit = document.createElement("i");
      bit.className = "tgr__bit";
      var angle = (Math.PI * 2 * i) / 16 + Math.random() * 0.5;
      var dist = 70 + Math.random() * 90;
      bit.style.setProperty("--dx", Math.cos(angle) * dist + "px");
      bit.style.setProperty("--dy", Math.sin(angle) * dist * 0.8 + "px");
      bit.style.setProperty("--rot", (Math.random() * 540 - 270) + "deg");
      bit.style.setProperty("--t", (0.95 + Math.random() * 0.4).toFixed(2) + "s");
      bit.style.borderRadius = i % 3 === 0 ? "50%" : "2px";
      bit.style.background = colours[i % colours.length];
      bit.style.animationDelay = (i * 12) + "ms";
      host.appendChild(bit);
      (function (node) {
        setTimeout(function () {
          if (node.parentNode) node.parentNode.removeChild(node);
        }, 1500);
      })(bit);
    }
  }

  // Rays fire outward from the star the visitor chose.
  function rays(star) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    for (var i = 0; i < 8; i++) {
      var ray = document.createElement("i");
      ray.className = "tgr__ray";
      ray.style.setProperty("--rot", i * 45 + "deg");
      ray.style.animationDelay = (i * 18) + "ms";
      star.appendChild(ray);
      (function (node) {
        setTimeout(function () {
          if (node.parentNode) node.parentNode.removeChild(node);
        }, 900);
      })(ray);
    }
  }

  function build() {
    var id = toolId();
    var mine = readLocal(id);
    // "new"  — never rated, a tap adds a first review
    // "edit" — rated, still inside the 24h window, a tap edits that review
    // "again"— rated, window closed, a tap adds a fresh review
    function modeFor(entry) {
      if (!entry) return "new";
      return withinWindow(entry.at) ? "edit" : "again";
    }

    var root = document.createElement("section");
    root.className = "tgr";
    root.setAttribute("aria-label", "Rate this tool");
    var isHome = id === "home";
    root.innerHTML =
      '<div class="tgr__inner">' +
      '<span class="tgr__aura" aria-hidden="true"></span>' +
      '<span class="tgr__eyebrow"><i class="tgr__pulse"></i> One tap · one second</span>' +
      '<h2 class="tgr__title">' +
      (isHome ? "Enjoying ToolGuest?" : "Did this tool work for you?") +
      "</h2>" +
      '<p class="tgr__sub"></p>' +
      '<div class="tgr__stars" role="group" aria-label="Rate from 1 to 5 stars"></div>' +
      '<div class="tgr__meta"></div>' +
      '<div class="tgr__meter"><div class="tgr__meterFill"></div></div>' +
      "</div>";

    var inner = root.querySelector(".tgr__inner");
    var starRow = root.querySelector(".tgr__stars");
    var meta = root.querySelector(".tgr__meta");
    var sub = root.querySelector(".tgr__sub");
    var fill = root.querySelector(".tgr__meterFill");
    var buttons = [];

    // The subtitle tells the visitor which of the three things a tap will do,
    // because "change it any time" is no longer the whole truth once the edit
    // window has closed.
    function setSubtitle(entry) {
      var m = modeFor(entry);
      if (m === "edit") {
        sub.textContent = "You rated this " + entry.stars + " star" + (entry.stars === 1 ? "" : "s") + " — tap a star to update it.";
      } else if (m === "again") {
        sub.textContent = "Tap a star to leave a fresh review.";
      } else {
        // First visit, so there is nothing to explain yet — this is the moment
        // for the tool's own line rather than an instruction.
        sub.textContent = quoteFor(id);
      }
    }

    for (var n = 1; n <= STARS; n++) {
      var b = starButton(n);
      b.style.setProperty("--i", String(n - 1));
      starRow.appendChild(b);
      buttons.push(b);
    }

    // A few drifting sparks keep the card quietly alive.
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      for (var s = 0; s < 6; s++) {
        var spark = document.createElement("i");
        spark.className = "tgr__spark";
        spark.style.left = 8 + Math.random() * 84 + "%";
        spark.style.top = 20 + Math.random() * 60 + "%";
        spark.style.setProperty("--dur", (7 + Math.random() * 5).toFixed(1) + "s");
        spark.style.setProperty("--delay", (Math.random() * 7).toFixed(1) + "s");
        inner.appendChild(spark);
      }
    }

    // Filling runs left to right: each lit star pops in a beat after the one
    // before it, so a 5-star tap reads as a wave rather than one flat block.
    // The class is removed once the wave is over — an animation with
    // fill-mode `both` would otherwise keep overriding the hover transform.
    function paint(value, animate) {
      var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      buttons.forEach(function (b, i) {
        var on = i < value;
        b.classList.remove("is-sweep");
        b.style.removeProperty("--sd");
        b.classList.toggle("is-lit", on);
        if (on && animate && !still) {
          void b.offsetWidth; // restart the animation when re-lighting
          b.style.setProperty("--sd", i * 70 + "ms");
          b.classList.add("is-sweep");
          (function (node, delay) {
            setTimeout(function () {
              node.classList.remove("is-sweep");
            }, delay + 560);
          })(b, i * 70);
        }
      });
    }

    // Every meta line goes through setMeta so a hover preview can be shown and
    // then undone without losing whatever the widget was displaying.
    var metaBase = null;

    function setMeta(html) {
      metaBase = html;
      if (!starRow.dataset.hover) meta.innerHTML = html;
    }

    // `entry` is the local { stars, at } record, or null. It decides both the
    // "you: N ★" line and whether that score can still be edited.
    function showStats(count, average, entry) {
      var value = entry ? entry.stars : 0;
      if (!count) {
        setMeta(
          value
            ? '<span class="tgr__avg">You rated ' + value + " ★</span>" +
              '<span class="tgr__dot">·</span>' +
              '<span class="tgr__count">' +
              (modeFor(entry) === "edit" ? "tap a star to change it" : "tap a star to review again") +
              "</span>"
            : "<span>No ratings yet — be the first.</span>"
        );
        fill.style.width = "0%";
        return;
      }
      var yours = value
        ? '<span class="tgr__dot">·</span><span class="tgr__count">you: ' + value + " ★</span>"
        : "";
      setMeta(
        '<span class="tgr__avg">' + average.toFixed(1) + ' ★</span>' +
          '<span class="tgr__dot">·</span>' +
          '<span class="tgr__count">' + count + " rating" + (count === 1 ? "" : "s") + "</span>" +
          yours
      );
      fill.style.width = Math.round((average / STARS) * 100) + "%";
    }

    function showThanks(value) {
      setMeta('<span class="tgr__thanks"><span class="tgr__check">✓</span> ' + thanksFor(value) + "</span>");
    }

    // Hover preview: light every star up to the one under the cursor and name
    // the score. On mouse-out the row falls back to the visitor's saved rating,
    // never to an empty row, so a saved score can never be lost by accident.
    starRow.addEventListener("mouseover", function (e) {
      var b = e.target.closest(".tgr__star");
      if (!b) return;
      starRow.dataset.hover = b.dataset.value;
      var n = Number(b.dataset.value);
      meta.innerHTML = '<span class="tgr__preview">' + n + (n === 1 ? " star" : " stars") + "</span>";
    });
    starRow.addEventListener("mouseleave", function () {
      delete starRow.dataset.hover;
      if (metaBase !== null) meta.innerHTML = metaBase;
      var current = readLocal(id);
      paint(current ? current.stars : 0, false);
    });

    // Rating is always editable, never destructive, and never stuck: inside the
    // edit window a tap edits the score, after it a tap adds a new review.
    // There is no "tap again to remove" path. The server decides edit vs new;
    // the widget predicts it so the copy is honest while the request is in
    // flight, then adopts whatever the server says.
    function rate(value) {
      var previous = readLocal(id);
      var prevMode = modeFor(previous);
      var expected = prevMode === "again" ? "again" : prevMode === "edit" ? "edit" : "new";
      var at = expected === "edit" && previous ? previous.at : Date.now();

      writeLocal(id, value, at);
      setSubtitle({ stars: value, at: at });
      paint(value, true);
      root.classList.add("is-lit");

      buttons[value - 1].classList.add("is-pop");
      setTimeout(function () {
        buttons[value - 1].classList.remove("is-pop");
      }, 640);

      // Confetti and rays are a first-time-only celebration, so a visitor who
      // keeps changing their mind does not get fireworks on every tap.
      if (expected === "new") {
        confetti(inner);
        rays(buttons[value - 1]);
      }
      delete starRow.dataset.hover;
      showThanks(value, expected);

      api("POST", { tool: id, stars: value })
        .then(function (data) {
          // The server is the source of truth for the window, so a device with a
          // wrong clock still ends up in the right mode. If it disagrees with the
          // guess, the copy is corrected on the spot.
          var confirmed = data.rereview ? "again" : data.changed ? "edit" : "new";
          var stamp = data.ratedAt || at;
          writeLocal(id, value, stamp);
          setSubtitle({ stars: value, at: stamp });
          if (confirmed !== expected) showThanks(value, confirmed);
          setTimeout(function () {
            showStats(data.count, data.average, { stars: value, at: stamp });
          }, 4200);
        })
        .catch(function () {
          setTimeout(function () {
            meta.innerHTML =
              '<span class="tgr__count">Saved in this browser — you rated ' + value + " ★</span>";
          }, 4200);
        });
    }

    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        rate(parseInt(b.dataset.value, 10));
      });
    });

    // Keyboard: arrow keys move through the stars.
    starRow.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var idx = buttons.indexOf(document.activeElement);
      if (idx === -1) return;
      e.preventDefault();
      var next = e.key === "ArrowRight" ? Math.min(idx + 1, STARS - 1) : Math.max(idx - 1, 0);
      buttons[next].focus();
    });

    setSubtitle(mine);
    paint(mine ? mine.stars : 0, false);
    if (mine) root.classList.add("is-lit");
    else meta.innerHTML = '<span class="tgr__count">Tap a star — it only takes a second.</span>';

    api("GET", null)
      .then(function (data) {
        // The server remembers the rating even when localStorage does not (a new
        // browser, or private mode), so adopt its record and let it set the mode.
        var entry = mine;
        if (data.yourRating) {
          entry = { stars: data.yourRating, at: data.ratedAt || Date.now() };
          writeLocal(id, entry.stars, entry.at);
          paint(entry.stars, false);
          root.classList.add("is-lit");
        }
        setSubtitle(entry);
        showStats(data.count || 0, data.average || 0, entry);
      })
      .catch(function () {
        if (mine) showStats(0, 0, mine);
        else meta.innerHTML = "<span>Your rating stays in this browser.</span>";
      });

    return root;
  }

  // Insert directly above the section that owns the "Why ..." heading, so the
  // widget reads as part of the tool rather than a footer afterthought.
  //
  // Climbing is bounded on purpose. A heading is often wrapped in a header
  // div, and that header sits inside the section — but on a few pages the
  // section itself sits in a page-wide container. Climbing "until a section
  // tag" therefore jumped straight past the tool to the top of the page. We
  // instead climb only while the wrapper still holds a single heading, which
  // stops at the real section every time.
  function whyAnchor(root) {
    var nodes = root.querySelectorAll("p, span, div, h2, h3, strong");
    var best = null;
    var bestScore = -1;

    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var text = (el.textContent || "").trim();
      if (!text || text.length > 80 || !/^why\b/i.test(text)) continue;
      if (el.children.length > 2) continue;

      var cls = typeof el.className === "string" ? el.className : "";
      var score = 100 - text.length;
      if (/eyebrow|kicker|label|tag|overline/i.test(cls)) score += 60;
      if (/uppercase/i.test(cls)) score += 25;

      if (score > bestScore) {
        bestScore = score;
        best = el;
      }
    }

    if (!best) return null;

    var anchor = best;
    for (var up = 0; up < 4; up++) {
      var parent = anchor.parentElement;
      if (!parent || parent === root || parent === document.body) break;
      if (parent.tagName === "MAIN" || parent.tagName === "SECTION") {
        // A section is the natural boundary — take it and stop.
        anchor = parent;
        break;
      }
      if (parent.querySelectorAll("h2, h3").length > 1) break;
      anchor = parent;
    }

    return anchor === root ? null : anchor;
  }

  // Pages with no "Why" heading: land just after the tool, before the next
  // content block, rather than at the very top or the very bottom of the page.
  function contentAnchor(root) {
    var container = root;
    for (var depth = 0; depth < 8 && container; depth++) {
      var kids = [];
      for (var k = 0; k < container.children.length; k++) {
        var tag = container.children[k].tagName;
        if (tag !== "SCRIPT" && tag !== "STYLE") kids.push(container.children[k]);
      }

      var toolIdx = -1;
      for (var i = 0; i < kids.length; i++) {
        if (kids[i].id === "tool" || kids[i].querySelector("#tool")) {
          toolIdx = i;
          break;
        }
      }
      if (toolIdx < 0) return null;

      for (var j = toolIdx + 1; j < kids.length; j++) {
        var s = kids[j];
        var cls = typeof s.className === "string" ? s.className : "";
        if (/tf-related|foot/.test(cls)) break;
        if (s.getAttribute("aria-label") === "Related tools") break;
        if (s.tagName === "H2" || s.tagName === "H3") return s;
        if (s.querySelector("h2, h3")) return s;
      }
      container = kids[toolIdx];
    }
    return null;
  }

  // Last resort: sit just above the related-tools strip or the footer, so the
  // widget still reads as the end of the tool's own content. Appending to the
  // very end of <body> would drop it below the related-tools grid.
  function tailAnchor() {
    return document.querySelector(".tf-related, [aria-label='Related tools'], .foot, footer");
  }

  // The widget is injected between two blocks that each carry 60-90px of
  // vertical padding on most templates, so the card ended up floating in a wide
  // empty band. Margins on the widget cannot reach padding on its neighbours,
  // so the neighbours' padding is cancelled instead.
  //
  // Two shapes have to be handled, and they need different treatment:
  //   1. the widget sits between two siblings — cancel the padding on the
  //      element just before it and the element just after it
  //   2. the widget is the first or last child of a container (it landed at the
  //      top of a section) — the container's own padding also applies, and the
  //      nearest content sits outside that container, so the space has to be
  //      cancelled on the container and re-applied on the real neighbour.
  //      Without this, case-converter showed 44px above the card: 22px from the
  //      previous section plus 22px from the section holding the widget.
  function nearestBefore(node) {
    for (var n = node; n && n.parentElement; n = n.parentElement) {
      if (n.previousElementSibling) return n.previousElementSibling;
      if (n.parentElement === document.body || n.parentElement.tagName === "MAIN") break;
    }
    return null;
  }

  function nearestAfter(node) {
    for (var n = node; n && n.parentElement; n = n.parentElement) {
      if (n.nextElementSibling) return n.nextElementSibling;
      if (n.parentElement === document.body || n.parentElement.tagName === "MAIN") break;
    }
    return null;
  }

  function tighten(node) {
    var root = document.documentElement;
    if (!root.classList.contains("tgr-gap")) root.classList.add("tgr-gap");

    var before = nearestBefore(node);
    var after = nearestAfter(node);
    if (before) before.classList.add("tgr-tight-bottom");
    if (after) after.classList.add("tgr-tight-top");

    var a, b;
    if (!node.previousElementSibling) {
      for (a = node.parentElement; a && a !== document.body; a = a.parentElement) {
        a.classList.add("tgr-flat-top");
      }
    }
    if (!node.nextElementSibling) {
      for (b = node.parentElement; b && b !== document.body; b = b.parentElement) {
        b.classList.add("tgr-flat-bottom");
      }
    }
  }

  function place(node) {
    var main = document.querySelector("main");
    var roots = [main, document.body].filter(Boolean);
    var i;

    // A "Why ..." heading also appears in some footers. Landing on it would
    // drop the card below the related tools, so only a spot inside <main>
    // counts while <main> exists.
    for (i = 0; i < roots.length; i++) {
      var anchor = whyAnchor(roots[i]);
      if (!anchor || !anchor.parentNode) continue;
      if (main && !main.contains(anchor)) continue;
      anchor.parentNode.insertBefore(node, anchor);
      tighten(node);
      return;
    }

    for (i = 0; i < roots.length; i++) {
      var after = contentAnchor(roots[i]);
      if (!after || !after.parentNode) continue;
      if (main && !main.contains(after)) continue;
      after.parentNode.insertBefore(node, after);
      tighten(node);
      return;
    }

    var tail = tailAnchor();
    if (tail && tail.parentNode && (!main || main.contains(tail))) {
      tail.parentNode.insertBefore(node, tail);
    } else if (main) {
      main.appendChild(node);
    } else {
      document.body.appendChild(node);
    }
    tighten(node);
  }

  // The footer year must never go stale, and editing 27 pages every January is
  // how it does. Every page loads this script, so the year is set from here.
  function stampYear() {
    var y = String(new Date().getFullYear());
    var nodes = document.querySelectorAll("[id='year']");
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].textContent !== y) nodes[i].textContent = y;
    }
  }

  function mount() {
    if (document.querySelector(".tgr")) return;

    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/assets/rating-widget.css";
    document.head.appendChild(link);

    var node = build();
    place(node);

    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              node.classList.add("is-in");
              // Release the staggered entrance so hover and click transforms
              // are not overridden by the finished animation.
              setTimeout(function () {
                node.classList.add("is-ready");
              }, 700);
              io.disconnect();
            }
          });
        },
        { rootMargin: "0px 0px -8% 0px" }
      );
      io.observe(node);
    } else {
      node.classList.add("is-in", "is-ready");
    }
  }

  stampYear();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      stampYear();
      mount();
    });
  } else {
    mount();
  }
})();
