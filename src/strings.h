#pragma once

// avr-libc exposes strcasecmp()/strncasecmp() from <string.h> and does not
// provide the POSIX <strings.h> header. Other supported Arduino cores may
// provide a native <strings.h>, so defer to it outside AVR builds.
#if defined(__AVR__)
#include <string.h>
#else
#include_next <strings.h>
#endif
