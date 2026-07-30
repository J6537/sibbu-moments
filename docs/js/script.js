/* ==========================================================================
   Sibbu Moments — Website-Skripte
   Reines Vanilla JavaScript, keine externen Abhängigkeiten.
   Module: Header-Scroll, Mobile-Navigation, Active-Link-Tracking,
   Scroll-Reveal, Newsletter-Formular, Back-to-Top, dynamischer
   Content-Loader für den späteren Website-Pflege-Agenten.
   ========================================================================== */

(function () {
  "use strict";

  var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Footer-Jahr ---------- */
  var yearEl = document.getElementById("year");
  if (yearEl) {
    yearEl.textContent = new Date().getFullYear();
  }

  /* ---------- Header: Hintergrund beim Scrollen ---------- */
  var header = document.getElementById("site-header");
  function updateHeaderState() {
    if (!header) return;
    header.classList.toggle("is-scrolled", window.scrollY > 12);
  }
  updateHeaderState();
  window.addEventListener("scroll", updateHeaderState, { passive: true });

  /* ---------- Mobile-Navigation ---------- */
  var navToggle = document.getElementById("nav-toggle");
  var mainNav = document.getElementById("main-nav");

  function closeNav() {
    if (!mainNav || !navToggle) return;
    mainNav.classList.remove("is-open");
    navToggle.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.setAttribute("aria-label", "Menü öffnen");
  }

  function toggleNav() {
    if (!mainNav || !navToggle) return;
    var isOpen = mainNav.classList.toggle("is-open");
    navToggle.classList.toggle("is-open", isOpen);
    navToggle.setAttribute("aria-expanded", String(isOpen));
    navToggle.setAttribute("aria-label", isOpen ? "Menü schließen" : "Menü öffnen");
  }

  if (navToggle) {
    navToggle.addEventListener("click", toggleNav);
  }

  if (mainNav) {
    mainNav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", closeNav);
    });
  }

  /* ---------- Aktiven Nav-Link je nach Scroll-Position markieren ---------- */
  var navLinks = mainNav ? Array.prototype.slice.call(mainNav.querySelectorAll("a[href^='#']")) : [];
  var sections = navLinks
    .map(function (link) {
      var id = link.getAttribute("href").slice(1);
      return document.getElementById(id);
    })
    .filter(Boolean);

  function setActiveLink() {
    var headerHeight = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--header-height")) || 84;
    var scrollPos = window.scrollY + headerHeight + 24;
    var currentId = null;

    sections.forEach(function (section) {
      if (section.offsetTop <= scrollPos) {
        currentId = section.id;
      }
    });

    navLinks.forEach(function (link) {
      var isActive = currentId && link.getAttribute("href") === "#" + currentId;
      link.classList.toggle("is-active", Boolean(isActive));
    });
  }

  if (sections.length) {
    window.addEventListener("scroll", setActiveLink, { passive: true });
    setActiveLink();
  }

  /* ---------- Scroll-Reveal via IntersectionObserver ---------- */
  var revealEls = document.querySelectorAll("[data-reveal]");

  if (prefersReducedMotion || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) {
      el.classList.add("is-visible");
    });
  } else {
    var revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -60px 0px" }
    );

    revealEls.forEach(function (el) {
      revealObserver.observe(el);
    });
  }

  /* ---------- Newsletter-Formular (rein clientseitig, kein Versand) ---------- */
  var newsletterForm = document.getElementById("newsletter-form");
  var newsletterNote = document.getElementById("newsletter-note");

  if (newsletterForm && newsletterNote) {
    newsletterForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var emailInput = document.getElementById("email-input");
      var email = emailInput ? emailInput.value.trim() : "";

      if (email) {
        newsletterNote.textContent = "Danke! Die Anmeldefunktion ist noch nicht aktiv — schau bald wieder vorbei.";
        newsletterForm.reset();
      }
    });
  }

  /* ---------- Zurück-nach-oben-Button ---------- */
  var backToTop = document.getElementById("back-to-top");
  if (backToTop) {
    backToTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
    });
  }

  /* ==========================================================================
     Dynamischer Content-Loader
     Lädt data/site-content.json und ersetzt die im HTML vorhandenen
     Standardtexte/-bilder durch die dort hinterlegten Werte. Schlägt das
     Laden fehl (fehlende/ungültige Datei, kein http(s)-Kontext) oder fehlt
     ein einzelnes Feld, bleibt einfach der bestehende, im HTML fest
     hinterlegte Text bzw. die Fallback-SVG-Illustration sichtbar — es gibt
     keinen Zustand, in dem ein Bereich leer oder kaputt aussieht.

     Sicherheitsprinzip: Texte werden ausschließlich über textContent
     gesetzt (nie innerHTML), Links werden gegen eine Protokoll-Positivliste
     geprüft (https:, mailto:, interner Anker, interner relativer Pfad) und
     Bildpfade gegen eine Ordner-/Endungs-Positivliste. Ungültige Werte
     werden stillschweigend ignoriert statt einen Fehler zu werfen.
     ========================================================================== */

  function isPlainObject(value) {
    return !!value && typeof value === "object" && !Array.isArray(value);
  }

  function safeText(value) {
    if (typeof value !== "string") return null;
    var trimmed = value.trim();
    return trimmed ? trimmed : null;
  }

  function safeRun(fn) {
    try {
      fn();
    } catch (err) {
      /* Ein einzelner unerwarteter Datenfehler darf die übrigen Bereiche
         nicht beeinträchtigen — dieser Abschnitt behält seinen Fallback. */
    }
  }

  /* Erlaubt: https://…, mailto:…, '#anker' (nicht der bloße Platzhalter '#')
     und interne relative Pfade. Verboten: javascript:, data:, http:, ftp:,
     doppelte Slashes, führendes '/', '..'-Pfadausbrüche. */
  function isSafeLink(url) {
    if (typeof url !== "string") return false;
    var v = url.trim();
    if (!v || v === "#") return false;
    if (v.charAt(0) === "#") return true;
    if (v.lastIndexOf("mailto:", 0) === 0) return v.length > "mailto:".length;
    if (v.lastIndexOf("https://", 0) === 0) return v.length > "https://".length;
    if (v.indexOf("://") !== -1) return false;
    if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return false;
    if (v.charAt(0) === "/") return false;
    if (v.indexOf("..") !== -1) return false;
    return true;
  }

  function setSafeLink(el, url) {
    if (!el) return;
    if (isSafeLink(url)) {
      var value = url.trim();
      el.setAttribute("href", value);
      el.removeAttribute("aria-disabled");
      el.removeAttribute("tabindex");
      var isExternal = false;
      if (value.lastIndexOf("https://", 0) === 0) {
        try {
          isExternal = new URL(value, window.location.href).hostname !== window.location.hostname;
        } catch (err) {
          isExternal = true;
        }
      }
      if (isExternal) {
        el.setAttribute("target", "_blank");
        el.setAttribute("rel", "noopener noreferrer");
      } else {
        el.removeAttribute("target");
        el.removeAttribute("rel");
      }
    } else {
      /* Kein gültiges Ziel vorhanden: Element bleibt sichtbar (keine
         Layout-Änderung), wird aber unschädlich gemacht statt ins Leere
         zu verlinken. */
      el.removeAttribute("href");
      el.setAttribute("aria-disabled", "true");
      el.setAttribute("tabindex", "-1");
    }
  }

  /* Bildpfade müssen relativ sein und in einem der vorgesehenen
     Bild-Ordner liegen (siehe content-schema.json → image_rules_common). */
  function safeImagePath(path) {
    if (typeof path !== "string") return null;
    var v = path.trim();
    if (!v) return null;
    if (v.indexOf("..") !== -1) return null;
    if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return null;
    if (v.charAt(0) === "/") return null;
    var allowedPrefixes = ["assets/images/web/", "assets/images/mobile/", "assets/images/original-derived/"];
    var hasAllowedPrefix = allowedPrefixes.some(function (prefix) {
      return v.lastIndexOf(prefix, 0) === 0;
    });
    if (!hasAllowedPrefix) return null;
    if (!/\.(webp|jpe?g|png)$/i.test(v)) return null;
    return v;
  }

  function setField(container, name, value) {
    if (!container) return;
    var target = container.querySelector('[data-field="' + name + '"]');
    if (!target) return;
    var text = safeText(value);
    if (text) target.textContent = text;
  }

  /* Setzt ein echtes Bild in den dafür vorgesehenen Medien-Slot ein und
     blendet die Fallback-Illustration aus. Ohne gültiges Bild + Alt-Text
     bleibt die Illustration unverändert sichtbar. */
  function setImageWithin(root, item, opts) {
    if (!root || !isPlainObject(item)) return;
    var mediaSlot = root.querySelector("[data-media-slot]");
    if (!mediaSlot) return;
    var fallback = root.querySelector("[data-fallback-art]");
    var src = safeImagePath(item.image);
    var alt = safeText(item.image_alt);
    if (!src || !alt) return;

    while (mediaSlot.firstChild) {
      mediaSlot.removeChild(mediaSlot.firstChild);
    }

    var picture = document.createElement("picture");
    var mobileSrc = safeImagePath(item.image_mobile);
    if (mobileSrc) {
      var source = document.createElement("source");
      source.setAttribute("srcset", mobileSrc);
      source.setAttribute("media", "(max-width: 640px)");
      picture.appendChild(source);
    }

    var img = document.createElement("img");
    img.setAttribute("src", src);
    img.setAttribute("alt", alt);
    img.setAttribute("loading", opts && opts.eager ? "eager" : "lazy");
    img.setAttribute("decoding", "async");
    img.addEventListener(
      "error",
      function () {
        /* Datei laut JSON vorhanden, lädt zur Laufzeit aber nicht (z. B.
           404) — zurück auf die Fallback-Illustration wechseln, statt ein
           kaputtes Bild-Icon anzuzeigen. */
        while (mediaSlot.firstChild) mediaSlot.removeChild(mediaSlot.firstChild);
        mediaSlot.hidden = true;
        if (fallback) fallback.hidden = false;
      },
      { once: true }
    );
    picture.appendChild(img);

    mediaSlot.appendChild(picture);
    mediaSlot.hidden = false;
    if (fallback) fallback.hidden = true;
  }

  function applyHero(hero) {
    if (!isPlainObject(hero)) return;
    var root = document.getElementById("top");
    if (!root) return;
    var textEl = root.querySelector('[data-content-id="hero-main"]');
    if (textEl) {
      setField(textEl, "subtitle", hero.subtitle);
      setField(textEl, "excerpt", hero.excerpt);
    }
    setImageWithin(root, hero, { eager: true });
  }

  function applyZitat(zitat, idMap) {
    if (!isPlainObject(zitat) || typeof zitat.id !== "string") return;
    var el = idMap[zitat.id];
    if (!el) return;
    setField(el, "body", zitat.body);
    setField(el, "subtitle", zitat.subtitle);
  }

  function applyCollection(wrapper, idMap, kind) {
    if (!isPlainObject(wrapper) || !Array.isArray(wrapper.items)) return;
    wrapper.items.forEach(function (item) {
      if (!isPlainObject(item) || typeof item.id !== "string") return;
      var card = idMap[item.id];
      if (!card) return; // Kein passender Slot im festen Layout vorhanden — wird ignoriert.

      setField(card, "location", item.location);
      setField(card, "title", item.title);
      setField(card, "excerpt", item.excerpt);
      setField(card, "category", item.category);

      var statusEl = card.querySelector('[data-field="content_status"]');
      if (statusEl) {
        if (kind === "journal") {
          var journalDate = safeText(item.date);
          if (item.content_status === "published" && journalDate) {
            statusEl.textContent = journalDate;
          }
        } else if (kind === "reisen") {
          var isSoon = item.content_status !== "published";
          statusEl.textContent = isSoon ? "Bald" : "Aktuell";
          statusEl.classList.toggle("story-status--soon", isSoon);
        }
      }

      var linkEl = card.querySelector('[data-field="link"]');
      if (linkEl) setSafeLink(linkEl, item.link);

      setImageWithin(card, item, { eager: false });
    });
  }

  function applyUeberUns(item, idMap) {
    if (!isPlainObject(item) || typeof item.id !== "string") return;
    var el = idMap[item.id];
    if (!el) return;
    setField(el, "body", item.body);
    var root = document.getElementById("ueber-uns");
    if (root) setImageWithin(root, item, { eager: false });
  }

  function applyKontakt(item, idMap) {
    if (!isPlainObject(item) || typeof item.id !== "string") return;
    var el = idMap[item.id];
    if (!el) return;
    setField(el, "excerpt", item.excerpt);
  }

  function applyContent(data) {
    if (!isPlainObject(data)) return;

    var idMap = {};
    document.querySelectorAll("[data-content-id]").forEach(function (el) {
      var id = el.getAttribute("data-content-id");
      if (id) idMap[id] = el;
    });

    safeRun(function () { applyHero(data.hero); });
    safeRun(function () { applyZitat(data.zitat, idMap); });
    safeRun(function () { applyCollection(data.reisen, idMap, "reisen"); });
    safeRun(function () { applyCollection(data.fotografie, idMap, "fotografie"); });
    safeRun(function () { applyCollection(data.journal, idMap, "journal"); });
    safeRun(function () { applyUeberUns(data["ueber-uns"], idMap); });
    safeRun(function () { applyKontakt(data.kontakt, idMap); });
  }

  function initDynamicContent() {
    if (typeof fetch !== "function") return;
    var src = (document.body && document.body.getAttribute("data-content-src")) || "data/site-content.json";

    fetch(src, { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        safeRun(function () { applyContent(data); });
      })
      .catch(function () {
        /* Datei fehlt, ist kein gültiges JSON, oder der Seitenkontext
           erlaubt kein fetch() (z. B. lokal über file://): die bestehenden,
           statisch im HTML hinterlegten Inhalte bleiben unverändert
           sichtbar. Das ist der gewünschte, sichere Normalzustand. */
      });
  }

  initDynamicContent();
})();
