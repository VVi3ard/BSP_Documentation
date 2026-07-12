from bsp_docs_mcp.cli import main


raise SystemExit(main(["crawl-its", *(__import__("sys").argv[1:])]))
