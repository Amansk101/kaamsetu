(function () {
  'use strict';

  var root = document.querySelector('[data-help-widget]');
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var activeRecognition = null;

  function voiceLanguage() {
    var picker = document.querySelector('[data-voice-language]');
    return picker ? picker.value : 'hi-IN';
  }

  function setVoiceStatus(button, message) {
    var wrap = button.closest('.ks-voice-wrap');
    var status = (wrap && wrap.querySelector('.ks-voice-status')) ||
      (button.closest('[data-help-widget]') && button.closest('[data-help-widget]').querySelector('.ks-voice-status'));
    if (status) {
      status.textContent = message;
      if (wrap) wrap.classList.toggle('has-voice-status', Boolean(message));
    }
  }

  function insertTranscript(field, transcript) {
    if (!field || !transcript) return;
    var start = typeof field.selectionStart === 'number' ? field.selectionStart : field.value.length;
    var end = typeof field.selectionEnd === 'number' ? field.selectionEnd : field.value.length;
    var before = field.value.slice(0, start);
    var after = field.value.slice(end);
    var spacer = before && !/\s$/.test(before) ? ' ' : '';
    var suffix = after && !/^\s/.test(after) ? ' ' : '';
    var phrase = spacer + transcript.trim() + suffix;
    if (typeof field.setRangeText === 'function') field.setRangeText(phrase, start, end, 'end');
    else field.value = before + phrase + after;
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function beginDictation(button, field) {
    if (!SpeechRecognition) {
      setVoiceStatus(button, 'Voice typing is not supported here. Try Chrome on Android or type instead.');
      return;
    }
    if (activeRecognition) activeRecognition.abort();
    var recognition = new SpeechRecognition();
    activeRecognition = recognition;
    recognition.lang = voiceLanguage();
    recognition.continuous = false;
    recognition.interimResults = false;
    button.setAttribute('aria-pressed', 'true');
    setVoiceStatus(button, 'Listening… speak now.');

    recognition.onresult = function (event) {
      var transcript = Array.prototype.map.call(event.results, function (result) {
        return result[0] && result[0].transcript ? result[0].transcript : '';
      }).join(' ').trim();
      insertTranscript(field, transcript);
      setVoiceStatus(button, transcript ? 'Voice text added. Please check it before saving.' : 'No speech heard. Tap the mic and try again.');
    };
    recognition.onerror = function (event) {
      var message = event.error === 'not-allowed' || event.error === 'service-not-allowed'
        ? 'Microphone permission is off. Allow it in your browser settings, then try again.'
        : event.error === 'no-speech' ? 'No speech heard. Tap the mic and try again.'
        : 'Voice typing stopped. Please try again or type instead.';
      setVoiceStatus(button, message);
    };
    recognition.onend = function () {
      button.setAttribute('aria-pressed', 'false');
      if (activeRecognition === recognition) activeRecognition = null;
    };
    try { recognition.start(); }
    catch (error) {
      button.setAttribute('aria-pressed', 'false');
      activeRecognition = null;
      setVoiceStatus(button, 'Could not start the microphone. Tap once and try again.');
    }
  }

  function addVoiceControls(container) {
    var scope = container || document;
    var fields = scope.querySelectorAll('input:not([type]), input[type="text"], input[type="search"], textarea');
    Array.prototype.forEach.call(fields, function (field) {
      if (field.disabled || field.readOnly || field.hasAttribute('data-no-voice') ||
          field.closest('[data-help-widget]') || field.closest('.ks-voice-wrap')) return;
      var wrapper = field.closest('.input-with-icon');
      if (!wrapper) {
        wrapper = document.createElement('span');
        wrapper.className = 'ks-voice-wrap';
        field.parentNode.insertBefore(wrapper, field);
        wrapper.appendChild(field);
      } else {
        wrapper.classList.add('ks-voice-wrap');
      }
      var mic = document.createElement('button');
      mic.type = 'button';
      mic.className = 'ks-voice-button';
      mic.setAttribute('data-voice-button', '');
      var fieldLabel = field.labels && field.labels.length ? field.labels[0].textContent.trim() : (field.name || 'this field');
      mic.setAttribute('aria-label', 'Speak to fill ' + fieldLabel);
      mic.setAttribute('aria-pressed', 'false');
      mic.title = 'Fill this field by voice';
      mic.innerHTML = '<i data-lucide="mic" aria-hidden="true"></i>';
      wrapper.appendChild(mic);
      var status = document.createElement('span');
      status.className = 'ks-voice-status';
      status.setAttribute('aria-live', 'polite');
      wrapper.appendChild(status);
    });
  }

  window.KaamSetuEnhanceVoiceInputs = function (container) {
    addVoiceControls(container || document);
    if (window.lucide && typeof window.lucide.createIcons === 'function') window.lucide.createIcons();
  };

  function initChat() {
    if (!root) return;
    var launcher = root.querySelector('[data-help-open]');
    var panel = root.querySelector('[data-help-panel]');
    var close = root.querySelector('[data-help-close]');
    var messages = root.querySelector('[data-help-messages]');
    var form = root.querySelector('[data-help-form]');
    var input = root.querySelector('[data-help-input]');
    var suggestions = root.querySelector('[data-help-suggestions]');
    var role = document.body.getAttribute('data-user-role') || 'visitor';
    var isHindi = (document.documentElement.lang || '').toLowerCase().startsWith('hi');
    var aiEnabled = root.getAttribute('data-ai-enabled') === 'true';
    var chatEndpoint = root.getAttribute('data-chat-endpoint');
    var history = [];

    function addMessage(message, isUser, links) {
      var item = document.createElement('div');
      item.className = 'ks-help-message' + (isUser ? ' is-user' : '');
      item.textContent = message;
      (links || []).forEach(function (link) {
        var anchor = document.createElement('a');
        anchor.href = link.href; anchor.textContent = link.label;
        item.appendChild(document.createElement('br')); item.appendChild(anchor);
      });
      messages.appendChild(item);
      messages.scrollTop = messages.scrollHeight;
      return item;
    }

    function answer(question) {
      var q = question.toLowerCase();
      var worker = role === 'worker' || /worker|kaam chahiye|naukri|job dhund|work|काम|नौकरी|काम ढूंढ/.test(q);
      var employer = role === 'employer' || /employer|hire|hiring|job post|kaam par|worker dhund|नियोक्ता|कामगार ढूंढ|भर्ती/.test(q);
      var reply, links = [];

      if (/mic|voice|microphone|bol ke|awaaz|awaz|speech|माइक|आवाज़|आवाज|बोलकर|बोल के/.test(q)) {
        reply = isHindi ? 'Mic button dabao, browser ko microphone permission do, aur Hindi ya apni voice language select karo. Jo bola hai woh field mein text ban kar aayega—save karne se pehle check kar lena.' : 'Tap the mic, allow microphone access, and choose your spoken language. Your speech is inserted as text; review it before saving.';
      } else if (/password|login|log in|sign in|account|पासवर्ड|लॉगिन|खाता/.test(q)) {
        reply = isHindi ? 'Login page par email aur password use karo. Password yaad nahi hai to reset link chuno.' : 'Use your email and password on the login page. Choose the password reset link if you cannot sign in.';
        links.push({href:'/accounts/login/',label:'Open login'});
      } else if (/video|skill demo|demo upload|वीडियो|कौशल/.test(q)) {
        reply = isHindi ? 'Worker dashboard se skill video upload karo. Video se suggest hui skills ko profile par dikhne se pehle review aur accept karna hota hai.' : 'Upload a short skill video from your worker area. Review and accept suggested skills before they appear on your profile.';
        links.push({href:'/worker/video/',label:'Go to skill video'});
      } else if (/consent|privacy|share|contact details|phone number|सहमति|गोपनीयता|निजी जानकारी|फोन नंबर/.test(q)) {
        reply = isHindi ? 'Worker decide karta hai ki employer ko kaunsi profile details dikhengi. Consent ke bina private details share nahi honi chahiye.' : 'Workers choose which profile details are shared with an employer. Private details should only be shared with the worker’s consent.';
        links.push({href:'/privacy/',label:'Read privacy information'});
      } else if (/fee|money|pay|otp|scam|fraud|safe|safety|deposit|फीस|पैसे|ओटीपी|धोखा|सुरक्षित|जमा/.test(q)) {
        reply = isHindi ? 'Kaam paane ke liye kisi ko registration fee, deposit ya OTP mat do. App job text par basic keyword checks karta hai; ye safety guarantee nahi hai. Doubt ho to details support ko bhejo.' : 'Do not pay a registration fee or deposit, and never share an OTP to get work. The app runs basic keyword checks, not a safety guarantee. Send concerns to support.';
        links.push({href:'mailto:support@kaamsetu.in',label:'Contact support'});
      } else if (/application|applicant|status|hired|candidate|आवेदन|स्थिति|उम्मीदवार/.test(q)) {
        if (worker) {
          reply = isHindi ? 'Worker dashboard ke Applications section mein apne application updates dekho.' : 'Open Applications in your worker area to check your application updates.';
          links.push({href:'/worker/applications/',label:'View my applications'});
        } else {
          reply = isHindi ? 'Employer dashboard ke Applications section mein applicants aur unka status dekho.' : 'Open Applications in your employer area to review applicants and update their status.';
          links.push({href:'/employer/applications/',label:'View applications'});
        }
      } else if (/profile|skills|edit details|update details|प्रोफाइल|कौशल|जानकारी/.test(q) && worker) {
        reply = isHindi ? 'Worker profile mein apne skills, location aur work preferences update karke Save Profile dabao.' : 'Update your skills, location and work preferences in your worker profile, then choose Save Profile.';
        links.push({href:'/worker/profile/',label:'Open my profile'});
      } else if (/profile|business|company|settings|edit details|update details|प्रोफाइल|कारोबार|जानकारी/.test(q) && employer) {
        reply = isHindi ? 'Employer settings mein business aur contact details update karke Save dabao.' : 'Update your business and contact details in employer settings, then save your changes.';
        links.push({href:'/employer/settings/',label:'Open employer settings'});
      } else if (/edit|close|manage|my jobs|job list/.test(q) && employer) {
        reply = isHindi ? 'Employer ke Jobs section mein apni listing kholo; wahan edit ya close kar sakte ho.' : 'Open your employer Jobs list, choose a listing, then edit or close it.';
        links.push({href:'/employer/jobs/',label:'Manage my jobs'});
      } else if (/find job|search job|apply|kaam dhund|job dhund|work|काम ढूंढ|नौकरी|काम खोज/.test(q) || (worker && /job|kaam|naukri|काम/.test(q))) {
        reply = isHindi ? 'Worker Jobs page par active jobs dekho. Job khol kar Apply dabao; application status dashboard mein milega.' : 'Open Worker Jobs to browse active roles. Open a job and choose Apply; check your dashboard for application updates.';
        links.push({href:'/worker/jobs/',label:'Browse jobs'});
      } else if (/post|create|new job|hire|worker dhund|नौकरी पोस्ट|कामगार ढूंढ/.test(q) || (employer && /job|worker|नौकरी|काम/.test(q))) {
        reply = isHindi ? 'Employer dashboard mein Post a Job se title, location, skills aur salary details bharo, phir publish karo.' : 'Choose Post a Job in the employer area. Add the role, location, skills and pay details, then publish.';
        links.push({href:'/employer/jobs/new/',label:'Post a job'});
      } else if (/help|problem|issue|stuck|support|मदद|समस्या|दिक्कत/.test(q)) {
        reply = isHindi ? 'Main profile, jobs, video, voice input aur consent ke steps mein help kar sakta hoon. Apni problem thodi detail mein likho; app se alag issue ho to support ko email karo.' : 'I can help with profiles, jobs, skill videos, voice input and consent. Describe what is stuck; email support for other account or technical issues.';
        links.push({href:'mailto:support@kaamsetu.in',label:'Email support'});
      } else {
        reply = isHindi ? 'Is sawal ka exact jawab mere help guide mein nahi mila. Profile, job search, job post, skill video, mic ya consent ke baare mein poochho—ya support ko email karo.' : 'I do not have a reliable answer for that yet. Ask about profiles, job search, posting a job, skill videos, the mic or consent—or email support.';
        links.push({href:'mailto:support@kaamsetu.in',label:'Email support'});
      }
      return {reply: reply, links: links};
    }

    function send(value) {
      var question = (value || '').trim();
      if (!question) return;
      addMessage(question, true);
      history.push({role: 'user', text: question});
      history = history.slice(-6);
      input.value = '';
      if (aiEnabled && chatEndpoint) {
        var pending = addMessage(isHindi ? 'Jawab taiyar ho raha hai…' : 'Thinking…', false);
        var csrf = form.querySelector('[name="csrfmiddlewaretoken"]');
        fetch(chatEndpoint, {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf ? csrf.value : ''},
          body: JSON.stringify({question: question, history: history})
        }).then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok || !data.ai || !data.answer) throw new Error('AI unavailable');
            return data.answer;
          });
        }).then(function (reply) {
          pending.textContent = reply;
          history.push({role: 'model', text: reply}); history = history.slice(-6);
          messages.scrollTop = messages.scrollHeight;
        }).catch(function () {
          var fallback = answer(question);
          pending.replaceChildren(); pending.textContent = fallback.reply;
          history.push({role: 'model', text: fallback.reply}); history = history.slice(-6);
          (fallback.links || []).forEach(function (link) {
            var anchor = document.createElement('a'); anchor.href = link.href; anchor.textContent = link.label;
            pending.appendChild(document.createElement('br')); pending.appendChild(anchor);
          });
          messages.scrollTop = messages.scrollHeight;
        });
      } else {
        var fallback = answer(question);
        addMessage(fallback.reply, false, fallback.links);
        history.push({role: 'model', text: fallback.reply}); history = history.slice(-6);
      }
      input.focus();
    }

    function addSuggestion(label) {
      var button = document.createElement('button'); button.type = 'button'; button.textContent = label;
      button.addEventListener('click', function () { send(label); suggestions.replaceChildren(); });
      suggestions.appendChild(button);
    }

    launcher.addEventListener('click', function () {
      panel.hidden = false; launcher.setAttribute('aria-expanded', 'true'); input.focus();
      if (!messages.childElementCount) {
        addMessage(isHindi ? 'Namaste! KaamSetu mein kis cheez ki help chahiye?' : 'Hi! What do you need help with on KaamSetu?', false);
        addSuggestion(role === 'employer' ? 'Post a job' : 'Find a job');
        addSuggestion('Use voice / mic'); addSuggestion('Profile help');
      }
    });
    close.addEventListener('click', function () { panel.hidden = true; launcher.setAttribute('aria-expanded', 'false'); launcher.focus(); });
    form.addEventListener('submit', function (event) { event.preventDefault(); send(input.value); });
    document.addEventListener('click', function (event) {
      var mic = event.target.closest('[data-voice-button]');
      if (!mic) return;
      var field = mic.classList.contains('ks-help-mic') ? input : mic.closest('.ks-voice-wrap').querySelector('input, textarea');
      beginDictation(mic, field);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !panel.hidden) close.click();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    addVoiceControls(document);
    initChat();
    if (window.lucide && typeof window.lucide.createIcons === 'function') window.lucide.createIcons();
  });
})();
