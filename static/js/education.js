/* Shared Country -> University -> Course controls, including Django admin. */
(() => {
  function initializeEducation() {
  document.querySelectorAll('form').forEach((form) => {
    const country = form.querySelector('[data-education="country"]');
    const university = form.querySelector('[data-education="university"]');
    const course = form.querySelector('[data-education="course"]');
    if (!country || !university || country.dataset.educationReady) return;
    country.dataset.educationReady = 'true';
    const feedback = document.createElement('p');
    feedback.className = 'help-text';
    feedback.setAttribute('role', 'status');
    university.insertAdjacentElement('afterend', feedback);
    const reset = (select, text) => {
      if (!select) return;
      select.replaceChildren(new Option(text, ''));
    };
    let version = 0;
    async function populate(select, url, generation) {
      if (!select) return;
      select.disabled = true;
      feedback.textContent = 'Loading education choices...';
      try {
        const options = [];
        while (url) {
          const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
          if (!response.ok) throw new Error('Choices unavailable');
          const data = await response.json();
          if (generation !== version) return;
          options.push(...data.results);
          // Pagination stays on our origin, including behind an HTTPS proxy.
          url = data.next ? new URL(data.next).pathname + new URL(data.next).search : null;
        }
        options.forEach((item) => select.add(new Option(item.program ? `${item.name} (${item.mode}, ${item.intake})` : item.name, item.id)));
        feedback.textContent = options.length ? '' : 'No active options available for this selection.';
      } catch (_) {
        if (generation === version) feedback.textContent = 'Could not load choices. Change the parent selection to retry.';
      } finally {
        if (generation === version) select.disabled = false;
      }
    }
    country.addEventListener('change', () => {
      const generation = ++version;
      reset(university, 'Select university');
      reset(course, 'Select course');
      university.disabled = false;
      if (course) course.disabled = false;
      feedback.textContent = '';
      if (country.value) populate(university, `/api/v1/education/countries/${encodeURIComponent(country.value)}/universities/`, generation);
    });
    university.addEventListener('change', () => {
      const generation = ++version;
      reset(course, 'Select course');
      if (course) course.disabled = false;
      feedback.textContent = '';
      if (university.value && course) populate(course, `/api/v1/education/universities/${encodeURIComponent(university.value)}/courses/`, generation);
    });
  });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeEducation, {once: true});
  } else {
    initializeEducation();
  }
})();
