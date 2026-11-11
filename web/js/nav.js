/* Top navigation: OTHERS dropdown (hover on desktop, click/tap, full keyboard) and the mobile menu.
 * Keyboard: Enter / Space / ArrowDown on OTHERS opens the menu and focuses the first item;
 * ArrowUp / ArrowDown / Home / End move; Esc closes and returns focus to OTHERS; Tab out closes. */
(function (ET) {
  "use strict";

  var N = ET.Nav = {};
  var OTHER_ROUTES = ["why-not-others", "limitations", "sources", "method"];
  var drop, btn, menu, links, toggle;

  function items() { return Array.prototype.slice.call(menu.querySelectorAll('[role="menuitem"]')); }

  function setOpen(open, focusFirst) {
    drop.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && focusFirst) { var first = items()[0]; if (first) first.focus(); }
  }

  function focusStep(step) {
    var list = items();
    var i = list.indexOf(document.activeElement);
    var next = i < 0 ? 0 : (i + step + list.length) % list.length;
    list[next].focus();
  }

  function onButtonKey(e) {
    // Enter and Space reach the click handler (a keyboard click has detail 0), so only arrows and Esc are handled here.
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true, true); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setOpen(true, false); items()[items().length - 1].focus(); }
    else if (e.key === "Escape") { setOpen(false); }
  }

  function onMenuKey(e) {
    if (e.key === "ArrowDown") { e.preventDefault(); focusStep(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); focusStep(-1); }
    else if (e.key === "Home") { e.preventDefault(); items()[0].focus(); }
    else if (e.key === "End") { e.preventDefault(); items()[items().length - 1].focus(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); btn.focus(); }
    else if (e.key === "Tab") { setOpen(false); }
  }

  /** Close everything (called after navigating). */
  N.close = function () {
    if (!drop) return;
    setOpen(false);
    links.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open menu");
  };

  /** Mark the current page: thin underline on MOON / MARS / OTHERS, highlight inside the menu. */
  N.setActive = function (route) {
    document.querySelectorAll("#nav [data-route]").forEach(function (a) {
      var on = a.dataset.route === route;
      a.classList.toggle("active", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    btn.classList.toggle("active", OTHER_ROUTES.indexOf(route) >= 0);
  };

  N.init = function () {
    drop = document.getElementById("nav-drop");
    btn = document.getElementById("nav-drop-btn");
    menu = document.getElementById("nav-drop-menu");
    links = document.getElementById("nav-links");
    toggle = document.getElementById("nav-toggle");

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      setOpen(!drop.classList.contains("open"), e.detail === 0);   // detail 0 = keyboard-triggered click
    });
    btn.addEventListener("keydown", onButtonKey);
    menu.addEventListener("keydown", onMenuKey);
    drop.addEventListener("focusout", function (e) { if (!drop.contains(e.relatedTarget)) setOpen(false); });
    document.addEventListener("click", function (e) { if (!drop.contains(e.target)) setOpen(false); });

    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      if (!open) setOpen(false);
    });
  };
})(window.ET);
