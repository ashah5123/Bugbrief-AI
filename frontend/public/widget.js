(function () {
  "use strict";
  var script = document.currentScript;
  var token = script && script.getAttribute("data-project");
  if (
    !script ||
    !token ||
    !/^[A-Za-z0-9_-]{43}$/.test(token) ||
    document.getElementById("bugbrief-launcher")
  )
    return;
  var base = new URL(script.src).origin;
  var host = document.createElement("div");
  host.id = "bugbrief-launcher";
  var root = host.attachShadow({ mode: "open" });
  var style = document.createElement("style");
  style.textContent =
    ":host{position:fixed;right:22px;bottom:22px;z-index:2147483000;font:13px system-ui}button{font:inherit;cursor:pointer} .launcher{background:#244b3d;color:#fff;border:1px solid #55715a;border-radius:30px;padding:14px 19px;box-shadow:0 4px 24px #193b3030;display:flex;align-items:center;gap:9px}.dot{width:8px;height:8px;border-radius:50%;background:#cdddab}.panel{position:fixed;right:22px;bottom:83px;width:min(460px,calc(100vw - 28px));height:min(740px,calc(100dvh - 110px));background:#f8f9f5;border:1px solid #d4deca;border-radius:15px;box-shadow:0 12px 70px #193b3040;overflow:hidden}.panel[hidden]{display:none}iframe{width:100%;height:100%;border:0}.close{position:absolute;right:12px;top:12px;border:0;border-radius:50%;width:27px;height:27px;background:#e9efdf;color:#506946;font-size:20px;z-index:2}@media(max-width:520px){:host{right:14px;bottom:14px}.panel{right:14px;bottom:73px;height:calc(100dvh - 95px)}}";
  var button = document.createElement("button");
  button.className = "launcher";
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-label", "Report a problem");
  var dot = document.createElement("span");
  dot.className = "dot";
  button.appendChild(dot);
  button.appendChild(document.createTextNode("Report a problem"));
  var panel = document.createElement("div");
  panel.className = "panel";
  panel.hidden = true;
  var close = document.createElement("button");
  close.className = "close";
  close.textContent = "×";
  close.setAttribute("aria-label", "Close feedback form");
  var frame = document.createElement("iframe");
  frame.title = "Report a problem";
  frame.referrerPolicy = "no-referrer";
  frame.src = base + "/c/" + encodeURIComponent(token) + "?embedded=1";
  panel.appendChild(close);
  panel.appendChild(frame);
  root.appendChild(style);
  root.appendChild(panel);
  root.appendChild(button);
  document.body.appendChild(host);
  function fitVisibleViewport() {
    var viewport = window.visualViewport;
    if (!viewport) return;
    var compact = viewport.width <= 520;
    var gap = compact ? 14 : 22;
    var right = Math.max(0, innerWidth - viewport.width - viewport.offsetLeft);
    var bottom = Math.max(0, innerHeight - viewport.height - viewport.offsetTop);
    host.style.right = right + gap + "px";
    host.style.bottom = bottom + gap + "px";
    panel.style.right = right + gap + "px";
    panel.style.bottom = bottom + (compact ? 73 : 83) + "px";
    panel.style.width = Math.min(460, viewport.width - 28) + "px";
    panel.style.height = Math.max(120, Math.min(740, viewport.height - (compact ? 95 : 110))) + "px";
  }
  fitVisibleViewport();
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", fitVisibleViewport);
    window.visualViewport.addEventListener("scroll", fitVisibleViewport);
  }
  function hide() {
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.focus();
  }
  button.addEventListener("click", function () {
    panel.hidden = !panel.hidden;
    button.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) frame.focus();
  });
  close.addEventListener("click", hide);
  window.addEventListener("message", function (event) {
    if (
      event.origin !== base ||
      event.source !== frame.contentWindow ||
      !event.data ||
      event.data.type !== "bugbrief:ready"
    )
      return;
    var page = new URL(window.location.href);
    var demo = page.origin === base && page.pathname === "/demo/" + token;
    frame.contentWindow.postMessage(
      {
        type: "bugbrief:context",
        pageUrl: page.origin + page.pathname,
        source: demo ? "demo" : "embedded",
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
      },
      base,
    );
  });
  root.addEventListener("keydown", function (event) {
    if (event.key === "Escape") hide();
  });
})();
