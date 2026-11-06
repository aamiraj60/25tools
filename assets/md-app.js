/* Page wiring for the Markdown to HTML converter.
 *
 * Depends on the MD object that the parser script defines.
 */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var md = $("md");
  var preview = $("preview");
  var htmlcode = $("htmlcode");
  var htmlcodeInner = $("htmlcodeInner");
  var printRoot = $("print-root");
  var grid = $("grid");
  var outTabs = $("outTabs");
  var viewSeg = $("viewSeg");
  var perfEl = $("perf");
  var mdStats = $("mdStats");
  var footStats = $("footStats");
  var toastEl = $("toast");
  var lastHtml = "";

  function options() {
    return {
      strip: $("optStrip").checked,
      tailwind: $("optTw").checked,
      minify: $("optMin").checked
    };
  }

  function render() {
    var started = performance.now();
    lastHtml = MD.renderMarkdown(md.value, options());
    var ms = performance.now() - started;
    preview.innerHTML = lastHtml;
    htmlcodeInner.textContent = lastHtml;
    perfEl.textContent = ms.toFixed(1) + " ms";
    updateStats();
  }

  function updateStats() {
    var text = md.value;
    var words = (text.trim().match(/\S+/g) || []).length;
    var chars = text.length;
    var lines = text ? text.split("\n").length : 0;
    mdStats.textContent = words + " words · " + chars + " chars";
    footStats.textContent = lines + " lines · " + words + " words";
  }

  function toast(message) {
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { toastEl.classList.remove("show"); }, 1900);
  }

  function copyText(text) {
    function viaTextarea() {
      var helper = document.createElement("textarea");
      helper.value = text;
      helper.setAttribute("readonly", "");
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(helper);
      return ok ? Promise.resolve() : Promise.reject(new Error("copy failed"));
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(viaTextarea);
    }
    return viaTextarea();
  }

  /* Rich copy keeps headings, lists and tables when pasted into a word
   * processor, and falls back to plain text everywhere else. */
  function copyRich() {
    var plain = preview.innerText;
    if (navigator.clipboard && window.ClipboardItem) {
      var item = new ClipboardItem({
        "text/html": new Blob([lastHtml], { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" })
      });
      return navigator.clipboard.write([item]).catch(function () { return copyText(plain); });
    }
    return copyText(plain);
  }

  function download(filename, text, type) {
    var blob = new Blob([text], { type: type || "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function pageHtml() {
    return "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
      + "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
      + "<title>Document</title>\n</head>\n<body>\n" + lastHtml + "\n</body>\n</html>\n";
  }

  function applyTemplate(name) {
    var tpl = $("tpl-" + name);
    if (!tpl) return;
    md.value = tpl.textContent.replace(/^\n/, "");
    render();
  }

  function setView(mode) {
    grid.classList.remove("view-editor", "view-preview");
    if (mode !== "split") grid.classList.add("view-" + mode);
    Array.prototype.forEach.call(viewSeg.querySelectorAll("button"), function (b) {
      b.classList.toggle("active", b.dataset.view === mode);
    });
  }

  function setTab(name) {
    var isHtml = name === "html";
    htmlcode.classList.toggle("hidden", !isHtml);
    preview.classList.toggle("hidden", isHtml);
    Array.prototype.forEach.call(outTabs.querySelectorAll("button"), function (b) {
      b.classList.toggle("active", b.dataset.tab === name);
    });
  }

  /* Keep the split honest: the gutter sets --lw as a share of the grid. */
  function initGutter() {
    var gutter = $("gutter");
    var dragging = false;
    gutter.addEventListener("mousedown", function (e) {
      dragging = true;
      gutter.classList.add("dragging");
      e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      var box = grid.getBoundingClientRect();
      var pct = ((e.clientX - box.left) / box.width) * 100;
      pct = Math.max(18, Math.min(82, pct));
      grid.style.setProperty("--lw", pct + "%");
    });
    window.addEventListener("mouseup", function () {
      dragging = false;
      gutter.classList.remove("dragging");
    });
  }

  /* The page ships a theme-color pair for the OS colour scheme. Once a visitor
   * picks a theme explicitly, that choice wins, so both metas are set to it. */
  function syncThemeColor(dark) {
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    Array.prototype.forEach.call(metas, function (m) {
      m.setAttribute("content", dark ? "#08080a" : "#ffffff");
    });
  }

  function initTheme() {
    var btn = $("themeBtn");
    syncThemeColor(document.documentElement.classList.contains("dark"));
    btn.addEventListener("click", function () {
      var dark = document.documentElement.classList.toggle("dark");
      $("icoMoon").classList.toggle("hidden", dark);
      $("icoSun").classList.toggle("hidden", !dark);
      try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch (e) {}
      syncThemeColor(dark);
    });
  }

  /* On phones the split pane collapses, so a pair of tabs chooses which pane is
   * visible. On wider screens both tabs are hidden and the grid takes over. */
  function initPaneTabs() {
    var tabs = $("paneTabs");
    if (!tabs) return;
    Array.prototype.forEach.call(tabs.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () {
        var mode = b.dataset.pane;
        grid.classList.remove("mobile-editor", "mobile-preview");
        grid.classList.add("mobile-" + mode);
        Array.prototype.forEach.call(tabs.querySelectorAll("button"), function (x) {
          x.classList.toggle("active", x === b);
        });
      });
    });
  }

  function initEvents() {
    md.addEventListener("input", render);
    md.addEventListener("scroll", function () {
      preview.scrollTop = md.scrollTop;
    });

    Array.prototype.forEach.call(viewSeg.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { setView(b.dataset.view); });
    });
    Array.prototype.forEach.call(outTabs.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { setTab(b.dataset.tab); });
    });

    ["optStrip", "optTw", "optMin"].forEach(function (id) {
      $(id).addEventListener("change", render);
    });

    $("templates").addEventListener("change", function (e) {
      if (e.target.value) applyTemplate(e.target.value);
      e.target.value = "";
    });
    $("heroTplBtn").addEventListener("click", function () {
      applyTemplate("readme");
      document.getElementById("editor").scrollIntoView({ behavior: "smooth" });
    });

    $("copyBtn").addEventListener("click", function () {
      copyText(lastHtml).then(function () { toast("HTML copied"); },
        function () { toast("Copy failed — select and copy"); });
    });
    $("copyPreviewBtn").addEventListener("click", function () {
      copyRich().then(function () { toast("Rendered preview copied"); },
        function () { toast("Copy failed — select and copy"); });
    });
    $("dlHtml").addEventListener("click", function () {
      download("document.html", pageHtml(), "text/html;charset=utf-8");
      toast("Downloaded document.html");
    });
    $("dlMd").addEventListener("click", function () {
      download("document.md", md.value, "text/markdown;charset=utf-8");
      toast("Downloaded document.md");
    });
    $("pdfBtn").addEventListener("click", function () {
      printRoot.innerHTML = lastHtml;
      window.print();
    });

    document.addEventListener("keydown", function (e) {
      if (!(e.metaKey || e.ctrlKey)) return;
      var key = e.key.toLowerCase();
      if (key === "b" || key === "i") {
        e.preventDefault();
        wrapSelection(key === "b" ? "**" : "*");
      } else if (key === "c" && e.shiftKey) {
        e.preventDefault();
        copyText(lastHtml).then(function () { toast("HTML copied"); });
      }
    });
  }

  function wrapSelection(marker) {
    var start = md.selectionStart;
    var end = md.selectionEnd;
    var value = md.value;
    var selected = value.slice(start, end) || "text";
    md.value = value.slice(0, start) + marker + selected + marker + value.slice(end);
    md.selectionStart = start + marker.length;
    md.selectionEnd = start + marker.length + selected.length;
    md.focus();
    render();
  }

  initTheme();
  initGutter();
  initPaneTabs();
  initEvents();
  applyTemplate("readme");
})();
