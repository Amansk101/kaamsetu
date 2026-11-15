/* KaamSetu — small vanilla-JS helpers (icons, mobile menu, language switch,
   password reveal, file/video preview + upload progress, toasts). */
(function () {
  'use strict';
  var dialog = document.querySelector('[data-auth-dialog]');
  var body = dialog && dialog.querySelector('[data-auth-dialog-body]');
  if (!dialog || !body) return;

  function loadAuthPage(url) {
    var target = new URL(url, window.location.href);
    target.searchParams.set('auth_modal', '1');
    fetch(target.href, { credentials: 'same-origin' }).then(function (response) {
      return response.text();
    }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var page = doc.querySelector('.auth-page');
      if (!page) { window.location.href = target.href; return; }
      body.replaceChildren(page);
      bindForm(body.querySelector('form'), target.href);
      if (window.lucide) window.lucide.createIcons();
      if (window.KaamSetuEnhanceVoiceInputs) window.KaamSetuEnhanceVoiceInputs(body);
      if (!dialog.open) {
        dialog.showModal();
        document.body.classList.add('auth-modal-open');
      }
      var heading = body.querySelector('h1');
      if (heading) {
        heading.id = 'auth-dialog-title';
        dialog.setAttribute('aria-labelledby', heading.id);
      }
      var firstField = body.querySelector('.auth-form input:not([type="hidden"]), .auth-form select, .auth-form a.button');
      if (firstField) firstField.focus();
    }).catch(function () { window.location.href = target.href; });
  }

  function bindForm(form, action) {
    if (!form) return;
    form.action = action;
    form.addEventListener('submit', function (event) {
          event.preventDefault();
          var data = new FormData(form);
          fetch(form.action, {
            method: 'POST', body: data, credentials: 'same-origin',
            headers: {'X-Requested-With': 'XMLHttpRequest'}
          }).then(function (response) {
            if (response.redirected) { window.location.href = response.url; return null; }
            return response.text();
          }).then(function (result) {
            if (!result) return;
            var nextDoc = new DOMParser().parseFromString(result, 'text/html');
            var nextPage = nextDoc.querySelector('.auth-page');
            if (nextPage) {
              body.replaceChildren(nextPage);
              bindForm(body.querySelector('form'), action);
              if (window.lucide) window.lucide.createIcons();
              if (window.KaamSetuEnhanceVoiceInputs) window.KaamSetuEnhanceVoiceInputs(body);
            }
          });
    });
  }

  dialog.addEventListener('click', function (event) {
    var reveal = event.target.closest('[data-reveal-password]');
    if (!reveal) return;
    var input = document.getElementById(reveal.getAttribute('data-reveal-password'));
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
    reveal.setAttribute('aria-pressed', input.type === 'text' ? 'true' : 'false');
    var showIcon = reveal.querySelector('[data-icon-show]');
    var hideIcon = reveal.querySelector('[data-icon-hide]');
    if (showIcon && hideIcon) {
      showIcon.classList.toggle('ks-hidden', input.type === 'text');
      hideIcon.classList.toggle('ks-hidden', input.type !== 'text');
    }
  });

  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-auth-modal-trigger]');
    var modalLink = dialog.open && event.target.closest('a[href]');
    if (!trigger && modalLink) {
      var modalUrl = new URL(modalLink.href, window.location.href);
      if (!/^\/accounts\/(login|register)\/$/.test(modalUrl.pathname)) modalLink = null;
      else trigger = modalLink;
    }
    if (!trigger) return;
    event.preventDefault();
    loadAuthPage(trigger.href);
  });
  dialog.querySelector('[data-auth-dialog-close]').addEventListener('click', function () { dialog.close(); });
  dialog.addEventListener('close', function () { document.body.classList.remove('auth-modal-open'); });
  dialog.addEventListener('click', function (event) { if (event.target === dialog) dialog.close(); });
})();

(function () {
  'use strict';

  function ready(fn) {
    if (document.readyState !== 'loading') { fn(); }
    else { document.addEventListener('DOMContentLoaded', fn); }
  }

  function renderIcons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }

  ready(function () {
    // --- Lucide icons (same icon set as the React reference app) ---------
    renderIcons();

    // --- Lazy background videos ------------------------------------------
    var backgroundVideos = Array.prototype.slice.call(
      document.querySelectorAll('[data-background-video]')
    );
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    var saveData = Boolean(connection && connection.saveData);

    function playBackgroundVideo(video) {
      if (document.hidden || reduceMotion || saveData) return;
      if (!video.getAttribute('src')) {
        var source = video.getAttribute('data-src');
        if (!source) return;
        video.setAttribute('src', source);
        video.load();
      }
      var playback = video.play();
      if (playback && typeof playback.catch === 'function') playback.catch(function () {});
    }

    backgroundVideos.forEach(function (video) {
      video.muted = true;
      video.defaultMuted = true;
      video.addEventListener('playing', function () { video.classList.add('is-ready'); });
      video.addEventListener('error', function () {
        video.classList.remove('is-ready');
        video.classList.add('is-video-failed');
      });
    });

    if (!reduceMotion && !saveData && backgroundVideos.length) {
      if ('IntersectionObserver' in window) {
        var videoObserver = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) playBackgroundVideo(entry.target);
            else entry.target.pause();
          });
        }, { rootMargin: '80px 0px', threshold: 0.01 });
        backgroundVideos.forEach(function (video) { videoObserver.observe(video); });
      } else {
        backgroundVideos.forEach(playBackgroundVideo);
      }
      document.addEventListener('visibilitychange', function () {
        backgroundVideos.forEach(function (video) {
          if (document.hidden) video.pause();
          else playBackgroundVideo(video);
        });
      });
    }

    // --- Mobile nav menu -------------------------------------------------
    var toggle = document.querySelector('[data-menu-toggle]');
    var menu = document.querySelector('[data-menu]');
    if (toggle && menu) {
      function setMobileMenu(open, restoreFocus) {
        menu.classList.toggle('is-open', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.setAttribute('aria-label', open ? (toggle.getAttribute('data-close-label') || 'Close menu') : (toggle.getAttribute('data-open-label') || 'Open menu'));
        if (restoreFocus) { toggle.focus(); }
      }
      toggle.addEventListener('click', function () {
        setMobileMenu(!menu.classList.contains('is-open'), false);
      });
      menu.addEventListener('click', function (event) {
        if (event.target.closest('a')) { setMobileMenu(false, false); }
      });
      document.addEventListener('click', function (event) {
        if (menu.classList.contains('is-open') && !menu.contains(event.target) && !toggle.contains(event.target)) {
          setMobileMenu(false, false);
        }
      });
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && menu.classList.contains('is-open')) {
          setMobileMenu(false, true);
        }
      });
      var mobileNavMedia = window.matchMedia('(max-width: 700px)');
      var syncMobileNav = function () {
        if (!mobileNavMedia.matches) { setMobileMenu(false, false); }
      };
      if (mobileNavMedia.addEventListener) { mobileNavMedia.addEventListener('change', syncMobileNav); }
      else if (mobileNavMedia.addListener) { mobileNavMedia.addListener(syncMobileNav); }
    }

    // --- Dashboard sidebar: persistent desktop collapse + mobile drawer --
    var dashboardToggle = document.querySelector('[data-dashboard-sidebar-toggle]');
    var dashboardClose = document.querySelector('[data-dashboard-sidebar-close]');
    var dashboardShell = document.querySelector('.dashboard-layout');
    var dashboardSidebar = document.querySelector('.dashboard-sidebar');
    if (dashboardToggle && dashboardShell && dashboardSidebar) {
      var dashboardMobile = window.matchMedia('(max-width: 850px)');
      var sidebarStorageKey = 'kaamsetu-dashboard-sidebar-collapsed';

      function closeDashboardSidebar() {
        dashboardShell.classList.remove('sidebar-open');
        document.body.classList.remove('dashboard-menu-open');
        dashboardToggle.setAttribute('aria-expanded', 'false');
      }

      function syncDashboardSidebar() {
        if (dashboardMobile.matches) {
          dashboardShell.classList.remove('sidebar-collapsed');
          closeDashboardSidebar();
        } else {
          document.body.classList.remove('dashboard-menu-open');
          dashboardShell.classList.remove('sidebar-open');
          dashboardShell.classList.toggle('sidebar-collapsed', localStorage.getItem(sidebarStorageKey) === 'true');
          dashboardToggle.setAttribute('aria-expanded', dashboardShell.classList.contains('sidebar-collapsed') ? 'false' : 'true');
        }
      }

      dashboardToggle.addEventListener('click', function () {
        if (dashboardMobile.matches) {
          var open = dashboardShell.classList.toggle('sidebar-open');
          document.body.classList.toggle('dashboard-menu-open', open);
          dashboardToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        } else {
          var collapsed = dashboardShell.classList.toggle('sidebar-collapsed');
          localStorage.setItem(sidebarStorageKey, collapsed ? 'true' : 'false');
          dashboardToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        }
      });
      if (dashboardClose) { dashboardClose.addEventListener('click', closeDashboardSidebar); }
      dashboardSidebar.querySelectorAll('a').forEach(function (link) {
        link.addEventListener('click', function () {
          if (dashboardMobile.matches) { closeDashboardSidebar(); }
        });
      });
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { closeDashboardSidebar(); }
      });
      dashboardMobile.addEventListener('change', syncDashboardSidebar);
      syncDashboardSidebar();
    }

    // --- Language switcher: submit on change -----------------------------
    document.querySelectorAll('[data-language-select]').forEach(function (select) {
      select.addEventListener('change', function () {
        if (select.form) { select.form.submit(); }
      });
    });

    document.querySelectorAll('[data-auto-submit-filters] select').forEach(function (select) {
      select.addEventListener('change', function () {
        if (select.form && typeof select.form.requestSubmit === 'function') select.form.requestSubmit();
      });
    });

    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (!window.confirm(form.getAttribute('data-confirm'))) event.preventDefault();
      });
    });

    // --- Toasts: dismiss ------------------------------------------------
    document.querySelectorAll('[data-dismiss-toast]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var toast = btn.closest('.ks-toast');
        if (toast) { toast.remove(); }
      });
    });
    setTimeout(function () {
      document.querySelectorAll('.ks-toast').forEach(function (t) {
        t.style.transition = 'opacity .4s ease';
        t.style.opacity = '0';
        setTimeout(function () { t.remove(); }, 400);
      });
    }, 6000);

    // --- Password reveal buttons ----------------------------------------
    document.querySelectorAll('[data-reveal-password]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var input = document.getElementById(btn.getAttribute('data-reveal-password'));
        if (!input) { return; }
        var show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        btn.setAttribute('aria-pressed', show ? 'true' : 'false');
        var on = btn.querySelector('[data-icon-show]');
        var off = btn.querySelector('[data-icon-hide]');
        if (on && off) {
          on.classList.toggle('ks-hidden', show);
          off.classList.toggle('ks-hidden', !show);
        }
      });
    });

    // --- Auth forms: inline validation, strength meter, submit lock ------
    // Server-side validation hi final authority hai; ye sirf turant feedback
    // deta hai aur double-submit rokata hai (rules backend se mirror hain).
    var NAME_RE = /^[\p{L}\p{M}]+(?:[ '\u2019.-][\p{L}\p{M}]+)*$/u;
    var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$/;
    var MOBILE_RE = /^[6-9]\d{9}$/;

    function fieldErrorEl(input) {
      var label = input.closest('label');
      var anchor = input.closest('.input-with-icon') || input;
      var target = label || anchor;
      var next = target.nextElementSibling;
      while (next && next.classList.contains('form-error') && !next.hasAttribute('data-js-error')) {
        // Server-rendered error ko mark karo taaki client valid hone par hata sakein.
        next.setAttribute('data-server-error', '');
        next = next.nextElementSibling;
      }
      var el = target.parentNode.querySelector('[data-js-error][data-for="' + input.id + '"]');
      if (!el) {
        el = document.createElement('p');
        el.className = 'form-error';
        el.setAttribute('role', 'alert');
        el.setAttribute('data-js-error', '');
        el.setAttribute('data-for', input.id);
        target.insertAdjacentElement('afterend', el);
      }
      return el;
    }

    function clearServerError(input) {
      var label = input.closest('label') || input;
      var next = label.nextElementSibling;
      while (next && next.classList.contains('form-error') && !next.hasAttribute('data-js-error')) {
        next.remove();
        next = label.nextElementSibling;
      }
    }

    function validateField(input, form) {
      var kind = input.getAttribute('data-validate');
      var value = input.value;
      var message = '';

      if (kind === 'name') {
        var name = value;
        if (!name.trim()) { message = 'Please enter your name.'; }
        else if (name !== name.trim()) { message = 'Name cannot start or end with a space.'; }
        else if (!NAME_RE.test(name)) {
          message = 'Use letters, single spaces, apostrophes, hyphens or periods in your name.';
        } else if (name.length < 2) {
          message = 'Please enter your name (at least 2 characters).';
        }
      } else if (kind === 'email') {
        var email = value;
        if (!email) { message = 'Please enter your email address.'; }
        else if (!EMAIL_RE.test(email)) {
          message = 'Enter a valid email address, e.g. you@example.com.';
        }
      } else if (kind === 'mobile') {
        var mobile = value;
        if (!mobile) { message = 'Please enter your mobile number.'; }
        else if (!MOBILE_RE.test(mobile)) {
          message = 'Enter a valid 10-digit mobile number starting with 6, 7, 8 or 9.';
        }
      } else if (kind === 'mobile-optional') {
        if (value && !MOBILE_RE.test(value)) {
          message = 'Enter a valid 10-digit mobile number starting with 6, 7, 8 or 9.';
        }
      } else if (kind === 'password') {
        if (!value) { message = 'Please choose a password.'; }
        else if (value.length < 8) { message = 'Password must be at least 8 characters long.'; }
        else if (!/[A-Z]/.test(value)) { message = 'Include at least one uppercase letter (A-Z).'; }
        else if (!/[a-z]/.test(value)) { message = 'Include at least one lowercase letter (a-z).'; }
        else if (!/[0-9]/.test(value)) { message = 'Include at least one number (0-9).'; }
        else if (!/[^A-Za-z0-9]/.test(value)) { message = 'Include at least one special character (e.g. @ # $ %).'; }
      } else if (kind === 'confirm') {
        var pw = form.querySelector('[data-validate="password"]');
        if (!value) { message = 'Please re-enter your password.'; }
        else if (pw && value !== pw.value) { message = 'Passwords do not match.'; }
      } else if (kind === 'login-password') {
        if (!value) { message = 'Please enter your password.'; }
      }

      var el = fieldErrorEl(input);
      if (message) {
        el.textContent = message;
        input.setAttribute('aria-invalid', 'true');
        input.classList.add('is-invalid');
      } else {
        el.textContent = '';
        input.removeAttribute('aria-invalid');
        input.classList.remove('is-invalid');
        clearServerError(input);
      }
      return !message;
    }

    function updatePasswordMeter(form) {
      var list = form.querySelector('[data-password-rules]');
      if (!list) { return; }
      var pw = form.querySelector('[data-validate="password"]');
      var confirm = form.querySelector('[data-validate="confirm"]');
      var value = pw ? pw.value : '';
      var checks = {
        length: value.length >= 8,
        upper: /[A-Z]/.test(value),
        lower: /[a-z]/.test(value),
        number: /[0-9]/.test(value),
        special: /[^A-Za-z0-9]/.test(value),
        match: !!value && !!confirm && value === confirm.value,
      };
      list.querySelectorAll('[data-rule]').forEach(function (li) {
        var ok = !!checks[li.getAttribute('data-rule')];
        li.classList.toggle('is-ok', ok);
      });
    }

    document.querySelectorAll('[data-auth-form]').forEach(function (form) {
      var inputs = form.querySelectorAll('[data-validate]');
      var submitBtn = form.querySelector('[data-submit-btn]');
      var touched = {};

      inputs.forEach(function (input) {
        var kind = input.getAttribute('data-validate');

        input.addEventListener('blur', function () {
          touched[input.id] = true;
          validateField(input, form);
          updatePasswordMeter(form);
        });
        input.addEventListener('input', function () {
          if (touched[input.id]) { validateField(input, form); }
          // Password badla to confirm aur meter dobara check karo.
          if (kind === 'password') {
            var confirm = form.querySelector('[data-validate="confirm"]');
            if (confirm && touched[confirm.id]) { validateField(confirm, form); }
          }
          updatePasswordMeter(form);
        });
      });

      updatePasswordMeter(form);

      form.addEventListener('submit', function (event) {
        var firstInvalid = null;
        inputs.forEach(function (input) {
          touched[input.id] = true;
          if (!validateField(input, form) && !firstInvalid) { firstInvalid = input; }
        });
        if (firstInvalid) {
          event.preventDefault();
          firstInvalid.focus();
          return;
        }
        // Valid — double submission rok do aur loading state dikhao.
        if (submitBtn) {
          submitBtn.classList.add('is-loading');
          submitBtn.setAttribute('aria-busy', 'true');
          submitBtn.disabled = true;
        }
      });
    });

    // --- File inputs: show chosen file name ------------------------------
    document.querySelectorAll('[data-file-input]').forEach(function (input) {
      input.addEventListener('change', function () {
        var target = document.querySelector(input.getAttribute('data-file-input'));
        if (target && input.files && input.files.length) {
          target.textContent = input.files[0].name;
        }
      });
    });

    // --- Worker profile photo preview + immediate type/size feedback -----
    document.querySelectorAll('[data-photo-input]').forEach(function (input) {
      input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        var form = input.closest('form');
        var avatar = form && form.querySelector('[data-photo-avatar]');
        var feedback = form && form.querySelector('[data-photo-feedback]');
        if (!file || !avatar) return;

        var suffix = file.name.split('.').pop().toLowerCase();
        var validType = ['jpg', 'jpeg', 'png'].indexOf(suffix) !== -1
          && (!file.type || ['image/jpeg', 'image/png'].indexOf(file.type) !== -1);
        if (!validType || file.size > 5 * 1024 * 1024) {
          input.value = '';
          input.setAttribute('aria-invalid', 'true');
          if (feedback) {
            feedback.textContent = !validType
              ? 'Choose a JPG or PNG profile photo.'
              : 'Choose a profile photo smaller than 5 MB.';
            feedback.setAttribute('role', 'alert');
            feedback.classList.add('field-error');
          }
          return;
        }

        input.removeAttribute('aria-invalid');
        if (feedback) {
          feedback.textContent = file.name + ' · ' + (file.size / 1024 / 1024).toFixed(2) + ' MB';
          feedback.setAttribute('role', 'status');
          feedback.classList.remove('field-error');
        }
        var preview = avatar.querySelector('[data-profile-photo-preview]');
        if (!preview) {
          preview = document.createElement('img');
          preview.alt = 'Profile photo preview';
          preview.setAttribute('data-profile-photo-preview', '');
          avatar.replaceChildren(preview);
        }
        if (preview.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
        preview.dataset.objectUrl = URL.createObjectURL(file);
        preview.src = preview.dataset.objectUrl;
      });
    });

    // --- Skills video: validate, preview and submit the real upload ------
    var videoInput = document.querySelector('[data-video-input]');
    var dropzone = document.querySelector('[data-dropzone]');
    var selectedBox = document.querySelector('[data-video-file]');
    var emptyBox = document.querySelector('[data-video-empty]');
    var preview = document.querySelector('[data-video-preview]');
    var nameEl = document.querySelector('[data-video-name]');
    var sizeEl = document.querySelector('[data-video-size]');
    var noteEl = document.querySelector('[data-video-note]');
    var uploadForm = document.querySelector('[data-skill-video-form]');
    var uploadSubmit = document.querySelector('[data-upload-submit]');
    var uploadError = document.querySelector('[data-video-client-error]');
    var removeBtn = document.querySelector('[data-video-remove]');
    var previewUrl = null;
    var allowedVideo = /\.(mp4|mov|webm|mkv|avi|m4v|3gp|ogv)$/i;

    function showFile(file) {
      if (!file) { return; }
      var isVideo = allowedVideo.test(file.name || '');
      var valid = isVideo && file.size <= 100 * 1024 * 1024;
      if (!valid) {
        if (uploadError) {
          uploadError.textContent = !isVideo
            ? 'Choose a supported video file (MP4, MOV, WebM, MKV, AVI, M4V, 3GP or OGV).'
            : 'Choose a video smaller than 100 MB.';
          uploadError.classList.remove('ks-hidden');
        }
        if (videoInput) { videoInput.value = ''; }
        return;
      }
      if (uploadError) { uploadError.classList.add('ks-hidden'); uploadError.textContent = ''; }
      if (nameEl) { nameEl.textContent = file.name; }
      if (sizeEl) { sizeEl.textContent = (file.size / 1024 / 1024).toFixed(1) + ' MB'; }
      if (preview) {
        if (previewUrl) { URL.revokeObjectURL(previewUrl); }
        previewUrl = URL.createObjectURL(file);
        preview.src = previewUrl;
        preview.classList.remove('ks-hidden');
      }
      if (noteEl) { noteEl.classList.add('ks-hidden'); }
      if (selectedBox) { selectedBox.classList.remove('ks-hidden'); }
      if (emptyBox) { emptyBox.classList.add('ks-hidden'); }
      if (dropzone) { dropzone.classList.add('has-file'); }
    }

    function resetFile() {
      if (videoInput) { videoInput.value = ''; }
      if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
      if (preview) { preview.removeAttribute('src'); preview.classList.add('ks-hidden'); }
      if (selectedBox) { selectedBox.classList.add('ks-hidden'); }
      if (emptyBox) { emptyBox.classList.remove('ks-hidden'); }
      if (dropzone) { dropzone.classList.remove('has-file'); }
      if (uploadError) { uploadError.classList.add('ks-hidden'); uploadError.textContent = ''; }
    }

    if (videoInput) {
      videoInput.addEventListener('change', function () {
        showFile(videoInput.files && videoInput.files[0]);
      });
    }
    if (removeBtn) {
      removeBtn.addEventListener('click', resetFile);
    }
    if (uploadForm && videoInput) {
      uploadForm.addEventListener('submit', function (event) {
        var selected = videoInput && videoInput.files && videoInput.files[0];
        if (!selected) {
          event.preventDefault();
          if (uploadError) {
            uploadError.textContent = 'Choose a video before uploading.';
            uploadError.classList.remove('ks-hidden');
          }
          return;
        }
        if (uploadSubmit) {
          uploadSubmit.disabled = true;
          uploadSubmit.setAttribute('aria-busy', 'true');
          uploadSubmit.innerHTML = '<span class="loading-dot" aria-hidden="true"></span> Uploading and assessing…';
        }
      });
    }
    if (dropzone) {
      ['dragenter', 'dragover'].forEach(function (evt) {
        dropzone.addEventListener(evt, function (e) {
          e.preventDefault();
          dropzone.classList.add('is-dragging');
        });
      });
      ['dragleave', 'drop'].forEach(function (evt) {
        dropzone.addEventListener(evt, function (e) {
          e.preventDefault();
          dropzone.classList.remove('is-dragging');
        });
      });
      dropzone.addEventListener('drop', function (e) {
        var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (file && videoInput) {
          videoInput.files = e.dataTransfer.files;
          showFile(file);
        }
      });
    }

    // --- Save-job submit ------------------------------------------------
    document.querySelectorAll('[data-save-job]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var form = btn.closest('form');
        if (form) { form.submit(); }
      });
    });

    // --- Job details modal ----------------------------------------------
    function closeModal(modal) {
      if (!modal) { return; }
      modal.classList.add('ks-hidden');
      document.body.classList.remove('modal-open');
    }

    document.querySelectorAll('[data-job-details]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var modal = document.getElementById(btn.getAttribute('data-job-details'));
        if (!modal) { return; }
        modal.classList.remove('ks-hidden');
        document.body.classList.add('modal-open');
        var focusTarget = modal.querySelector('.job-details-close');
        if (focusTarget) { focusTarget.focus(); }
      });
    });

    document.querySelectorAll('[data-job-close]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        closeModal(btn.closest('[data-job-modal]'));
      });
    });

    document.querySelectorAll('[data-job-modal]').forEach(function (modal) {
      modal.addEventListener('mousedown', function (event) {
        if (event.target === modal) { closeModal(modal); }
      });
    });

    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') { return; }
      document.querySelectorAll('[data-job-modal]:not(.ks-hidden)').forEach(closeModal);
    });
  });
})();

/* --------------------------------------------------------------------------
   Scroll reveal — fades sections in as they enter the viewport.
   Enabled only when JS runs and the user prefers motion, so nothing is ever
   hidden when scripting or animations are unavailable.
   -------------------------------------------------------------------------- */
(function () {
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var targets = document.querySelectorAll('.reveal');
  if (reduce || !targets.length || !('IntersectionObserver' in window)) { return; }

  document.documentElement.classList.add('js-reveal');

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

  targets.forEach(function (el) { observer.observe(el); });
})();
