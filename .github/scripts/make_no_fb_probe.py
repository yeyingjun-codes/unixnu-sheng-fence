from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()
start = source.index('  /* Marker: fill the top of the frame buffer white. */')
end = source.index('#if PROBE_RESET == 1', start)
replacement = '  /* No-FB variant: PSCI before display access. */\n\n'
path.write_text(source[:start] + replacement + source[end:])
result = path.read_text()
assert 'No-FB variant' in result
assert '_Paint:' not in result
print('no-FB source mutation verified; framebuffer marker removed', flush=True)
