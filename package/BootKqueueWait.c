// SPDX-License-Identifier: MIT
// Read-only kqueue-wait resolver for the boot UI trace.
//
// A backboardd/SpringBoard main thread blocked in kevent_id (XNU syscall 375)
// waits on &kqfile->kqf_count, NOT on a Mach peer (so peer=-1 is expected).
// To name what it is actually waiting for, find the kqfile whose &kqf_count
// matches the thread's wait_event, then enumerate the knotes registered on
// that kqueue's selinfo.si_note chain and report each knote's filter type.
// EVFILT_MACHPORT (-8) points at a Mach port (another daemon); EVFILT_PROC /
// READ / USER / etc. point at a different kind of event source.
//
// READ-ONLY inspection only: no wakeup, no knote add/remove, no state change.
// Runs in the trace worker's thread context (never at interrupt time).
//
// This TU intentionally includes the real BSD private headers (the same set
// kern_event.c uses) so struct kqueue/kqfile/selinfo/knote/filedesc layouts
// come from the actual XNU source, never hard-coded offsets.

#include <stdint.h>
#include <machine/atomic.h>

#include <sys/param.h>
#include <sys/systm.h>
#include <sys/filedesc.h>
#include <sys/kernel.h>
#include <sys/proc_internal.h>
#include <sys/kauth.h>
#include <sys/malloc.h>
#include <sys/unistd.h>
#include <sys/file_internal.h>
#include <sys/fcntl.h>
#include <sys/select.h>
#include <sys/queue.h>
#include <sys/event.h>
#include <sys/eventvar.h>
#include <sys/event_private.h>

#include <string.h>

#ifndef BOOT_KQUEUE_WAIT_MAX_KNOTES
#define BOOT_KQUEUE_WAIT_MAX_KNOTES 8
#endif

// One decoded knote: its filter (EVFILT_*), the actual filter id, saved fflags,
// and the ident it watches. Reported as plain integers; the caller formats.
struct boot_kqueue_knote_info {
	int16_t filter;
	uint8_t filtid;
	uint32_t sfflags;
	uint64_t ident;
};

// Describe the kqueue a thread is blocked on, if its wait_event is a kqfile's
// &kqf_count. Returns the number of knotes decoded (0 = not a kqueue wait, or
// the kqueue could not be located). out must hold BOOT_KQUEUE_WAIT_MAX_KNOTES.
// Pure read-only: holds proc_fdlock only long enough to copy what it prints.
unsigned boot_kqueue_wait_describe(int pid, uint64_t wait_event,
    struct boot_kqueue_knote_info *out, unsigned max)
{
	if (!out || max == 0 || wait_event == 0) {
		return 0;
	}
	if (max > BOOT_KQUEUE_WAIT_MAX_KNOTES) {
		max = BOOT_KQUEUE_WAIT_MAX_KNOTES;
	}

	proc_t p = proc_find(pid);
	if (p == PROC_NULL) {
		return 0;
	}

	unsigned found = 0;
	proc_fdlock(p);

	struct fileproc **ofiles = p->p_fd.fd_ofiles;
	int nfiles = p->p_fd.fd_nfiles;
	if (ofiles != NULL && nfiles > 0) {
		// fd_nfiles can be large; the high-water mark bounds real entries.
		int limit = p->p_fd.fd_afterlast;
		if (limit <= 0 || limit > nfiles) {
			limit = nfiles;
		}
		for (int fd = 0; fd < limit && found == 0; ++fd) {
			struct fileproc *fp = ofiles[fd];
			if (fp == FILEPROC_NULL || fp->fp_glob == NULL) {
				continue;
			}
			if (FILEGLOB_DTYPE(fp->fp_glob) != DTYPE_KQUEUE) {
				continue;
			}
			struct kqfile *kqf = (struct kqfile *)fp->fp_glob->fg_data;
			if (kqf == NULL) {
				continue;
			}
			// The wait target: address of this kqueue's event counter.
			if ((uint64_t)(uintptr_t)&kqf->kqf_count != wait_event) {
				continue;
			}

			// Matched. Enumerate the registered knotes on this kqueue's
			// selinfo note list (read-only snapshot of the chain).
			struct knote *kn = SLIST_FIRST(&kqf->kqf_sel.si_note);
			unsigned guard = 0;
			while (kn != NULL && found < max && guard++ < 256) {
				out[found].filter = kn->kn_filter;
				out[found].filtid = kn->kn_filtid;
				out[found].sfflags = kn->kn_sfflags;
				out[found].ident = kn->kn_id;
				++found;
				kn = SLIST_NEXT(kn, kn_selnext);
			}
			break;
		}
	}

	proc_fdunlock(p);
	proc_rele(p);
	return found;
}

// Human-readable short name for a knote filter, for on-screen rows.
const char *boot_kqueue_filter_name(int filter)
{
	switch (filter) {
	case EVFILT_READ: return "READ";
	case EVFILT_WRITE: return "WRITE";
	case EVFILT_VNODE: return "VNODE";
	case EVFILT_PROC: return "PROC";
	case EVFILT_SIGNAL: return "SIGNAL";
	case EVFILT_TIMER: return "TIMER";
	case EVFILT_MACHPORT: return "MACHPORT";
	case EVFILT_FS: return "FS";
	case EVFILT_USER: return "USER";
	case EVFILT_VM: return "VM";
	case EVFILT_EXCEPT: return "EXCEPT";
	default: return "?";
	}
}
