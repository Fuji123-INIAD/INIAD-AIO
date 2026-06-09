import sys

sys.path.insert(0, "backend")

import main


html = """
<html>
  <body>
    <div class="content-wrapper">
      <section class="content container-fluid">
        <h1>マークアップ言語とHTML</h1>
        <a>Bookmark</a>
        <iframe src="https://docs.google.com/presentation/embed"></iframe>
        <a>« Previous</a>
        <a>Next »</a>
      </section>
    </div>
  </body>
</html>
"""

print(main.extract_text_from_html(html))
