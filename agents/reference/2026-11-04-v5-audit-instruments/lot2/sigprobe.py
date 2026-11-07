import asyncio, sqlite3, sys, time
from p2pwatch.adapters.driving.process.posix_process import PosixProcess
class R:
    def request_shutdown(self): print("shutdown requested (loop callback)", flush=True)
async def main():
    async with PosixProcess(R()):
        c = sqlite3.connect(sys.argv[1], autocommit=True)
        t = time.monotonic()
        try:
            c.execute("VACUUM INTO ?", (sys.argv[1] + ".copy",))
            print(f"copy finished after {time.monotonic()-t:.1f} s", flush=True)
        except BaseException as e:
            print(f"copy raised {type(e).__name__}: {e} after {time.monotonic()-t:.1f} s", flush=True); raise
        await asyncio.sleep(0)
        print("after copy, loop resumed", flush=True)
asyncio.run(main())
