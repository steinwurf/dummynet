import asyncio

from dummynet.v2.filesystem import LocalFile


def test_local_file_write_read_and_remove(tmp_path):
    async def scenario():
        file = LocalFile(str(tmp_path / "nested" / "endpoint.json"))

        assert file.path == str(tmp_path / "nested" / "endpoint.json")
        assert not await file.exists()

        await file.write_text("first")
        assert await file.exists()
        assert await file.read_text() == "first"

        await file.write_text("replacement")
        assert await file.read_text() == "replacement"

        await file.remove()
        assert not await file.exists()

        # Cleanup paths may already have been removed by another process.
        await file.remove(missing_ok=True)

    asyncio.run(scenario())
