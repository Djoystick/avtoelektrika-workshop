// Генерируется автоматически
window.problems = [];
fetch('../_data/problems.json')
  .then(r => r.json())
  .then(data => {
    window.problems = data;
    if (typeof render === 'function') render(data);
  })
  .catch(console.error);
