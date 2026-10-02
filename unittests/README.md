# unittests

```bash
python3 -m unittest discover -s unittests -v
```

| File | Covers |
|---|---|
| `test_search.py` | search edge cases: ß/ss, umlauts, old spellings, sound-alike, typos, renamed stations, false hits |
| `test_models.py` | reviewed values, traffic lights, review status, filename notes |
| `test_store.py` | saving, change detection (touched vs. changed files), import of v8/v9 data |
| `test_image_prep.py` | 16 MP pixel budget, thin lines of 1-bit scans, PDFs not enlarged |

All tests use generated images and invented entries - no BVG plans.
`test_store.py` uses a temporary data directory, the project's `data/` is not touched.
