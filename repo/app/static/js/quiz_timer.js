(function () {
  var timerRoot = document.getElementById('quiz-timer');
  if (!timerRoot) return;

  var display = document.getElementById('timer-display');
  var submitBtn = document.getElementById('submit-btn');
  var form = document.getElementById('quiz-submit-form');
  var paperId = timerRoot.getAttribute('data-paper-id');
  var seconds = parseInt(timerRoot.getAttribute('data-seconds-remaining') || '0', 10);
  var submitted = false;

  function fmt(s) {
    var m = Math.floor(s / 60);
    var r = s % 60;
    return String(m).padStart(2, '0') + ':' + String(r).padStart(2, '0');
  }

  function paint() {
    display.textContent = fmt(Math.max(0, seconds));
    display.classList.remove('text-warning', 'text-danger');
    if (seconds <= 60) {
      display.classList.add('text-danger');
      if (seconds === 60) {
        try { window.navigator.vibrate && window.navigator.vibrate(80); } catch (_e) {}
      }
    } else if (seconds <= 300) {
      display.classList.add('text-warning');
    }
  }

  function autoSubmit() {
    if (submitted) return;
    submitted = true;
    if (submitBtn) submitBtn.disabled = true;
    if (form) {
      if (window.htmx) {
        window.htmx.trigger(form, 'submit');
      } else {
        form.submit();
      }
    }
  }

  paint();
  setInterval(function () {
    seconds -= 1;
    paint();
    if (seconds <= 0) autoSubmit();
  }, 1000);

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) return;
    fetch('/quiz/' + paperId + '/time-check')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        seconds = parseInt(d.seconds_remaining || '0', 10);
        paint();
      })
      .catch(function () {});
  });

  document.body.addEventListener('htmx:responseError', function (evt) {
    var indicator = document.getElementById('autosave-indicator');
    if (!indicator) return;
    if (evt.detail && evt.detail.requestConfig && String(evt.detail.requestConfig.path || '').indexOf('/autosave') !== -1) {
      indicator.textContent = 'Save failed';
      indicator.classList.add('text-danger');
    }
  });
})();
