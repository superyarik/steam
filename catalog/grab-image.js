// Запускать в обычном браузере на странице модели MakerWorld / Thingiverse / Cults3D:
// вставить в консоль (F12 → Console) или сохранить как закладку с префиксом «javascript:».
// Копирует в буфер строку «<ключ> <url картинки>» для catalog/image-urls.txt.
(() => {
  const u = location.href;
  const rules = [
    [/makerworld\.com\/.*\/models\/(\d+)/, "mw-"],
    [/makerworld\.com\/.*\/collections\/(\d+)/, "mw-collection-"],
    [/thingiverse\.com\/thing:(\d+)/, "tv-"],
    [/cults3d\.com\/.*\/([^/?#]+)$/, "cults-"],
  ];
  const rule = rules.find(([re]) => re.test(u));
  if (!rule) return alert("Это не страница модели MakerWorld, Thingiverse или Cults3D");
  const key = rule[1] + u.match(rule[0])[1];
  const meta = document.querySelector('meta[property="og:image"], meta[name="twitter:image"]');
  if (!meta) return alert("На странице нет og:image — сохраните картинку вручную как images/" + key + ".jpg");
  const line = key + " " + meta.content;
  navigator.clipboard.writeText(line).then(() => alert("Скопировано:\n" + line), () => prompt("Скопируйте строку:", line));
})();
