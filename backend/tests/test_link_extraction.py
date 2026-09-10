from backend.app.services.jd_extraction import extract_html, select_adapter


def test_selects_boss_adapter_from_url() -> None:
    adapter = select_adapter("https://www.zhipin.com/job_detail/123.html")
    assert adapter.name == "boss-zhipin"


def test_selects_mokahr_adapter_from_url() -> None:
    adapter = select_adapter("https://jobs.example.mokahr.com/jobs/123")
    assert adapter.name == "mokahr"


def test_extracts_structured_content_with_universal_fallback() -> None:
    html = """
    <html><head><title>数据分析师</title></head><body>
      <main class="job-detail"><h1>数据分析师</h1><div class="job-description">负责指标体系建设和分析。</div></main>
      <aside class="recommend-jobs">推荐岗位，不应进入正文</aside>
    </body></html>
    """
    result = extract_html("https://careers.example.com/jobs/1", html)
    assert result.adapter == "universal"
    assert result.title == "数据分析师"
    assert "指标体系建设" in result.text
    assert "推荐岗位" not in result.text


def test_extracts_mokahr_label_value_content() -> None:
    html = """
    <html><body><section class="job-detail">
      <h1>后端工程师</h1>
      <div>职位描述</div><p>负责服务端开发与性能优化。</p>
      <div>职位信息</div><div>职位名称</div><div>职位名称</div><div>后端工程师</div>
    </section></body></html>
    """
    result = extract_html("https://deepseek.mokahr.com/jobs/1", html)
    assert result.adapter == "mokahr"
    assert result.title == "后端工程师"
    assert "性能优化" in result.text
