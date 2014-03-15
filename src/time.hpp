#ifndef TIME_HPP_
#define TIME_HPP_

#include <stdint.h>
#include <time.h>

typedef uint64_t ticks_t;

timespec clock_realtime();
time_t get_secs();

timespec clock_monotonic();
ticks_t get_ticks();

ticks_t secs_to_ticks(time_t secs);
double ticks_to_secs(ticks_t ticks);

typedef uint64_t microtime_t;
microtime_t current_microtime();

#endif  // TIME_HPP_
