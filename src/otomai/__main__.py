import asyncio
import sys
from otomai import scripts

if __name__ == "__main__":
    asyncio.run(scripts.main(sys.argv[1:]))
