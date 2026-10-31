#include <arpa/inet.h>
#include <CommonCrypto/CommonDigest.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <libproc.h>
#include <mach-o/dyld.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/attr.h>
#include <stdint.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* APP-01A: an app location is authority only after resolving the actual image.
 * PACKAGE_VERIFY below is an inert build probe, never an operational bypass. */
static const char *canonical_bundle = "/Applications/KRONOS.app";
static const char *canonical_executable = "/Applications/KRONOS.app/Contents/MacOS/KRONOS";

/* Installation identity is separate from repository identity. This exact
 * device/inode binding is approved for the retained installation only.
 * No environment, live stat observation or missing record may supply authority. */
static const char *admission_anchor = "/Users/imranali/Library/Application Support/KRONOS/runtime";
static const dev_t approved_admission_device = 16777232;
static const ino_t approved_admission_inode = 694844364;
#define ADMISSION_BACKEND_DESCRIPTOR 197
static int admission_descriptor = -1;
static dev_t operation_observed_device=0;
static ino_t operation_observed_inode=0;
static pid_t admission_child = 0;
static char ordinary_stop_header[300];
static int admission_ready = 0;
static int admission_child_observed = 0;
static int admission_child_status = 0;
static int native_startup_active(void);
static int native_terminal_cleanup(void);
#define ADMISSION_CLEANUP_COMPLETE_EXIT 78


/* E02: actual opened-object attributes; no path/stat-derived volume assertion. */
static int descriptor_filesystem_identity(int fd,char volume[37],uint64_t *file_id) {
    struct attrlist request={0};unsigned char raw[128];uint32_t length,masks[5];
    request.bitmapcount=ATTR_BIT_MAP_COUNT;
    request.commonattr=ATTR_CMN_RETURNED_ATTRS|ATTR_CMN_FILEID;
    memset(raw,0,sizeof(raw));
    if(fgetattrlist(fd,&request,raw,sizeof(raw),0)!=0)return 0;
    memcpy(&length,raw,4);memcpy(masks,raw+4,20);
    if(length!=32 || masks[0]!=(ATTR_CMN_RETURNED_ATTRS|ATTR_CMN_FILEID) ||
       masks[1] || masks[2] || masks[3] || masks[4])return 0;
    memcpy(file_id,raw+24,8);
    struct stat st;if(!*file_id || fstat(fd,&st)!=0 || *file_id!=(uint64_t)st.st_ino)return 0;
    memset(&request,0,sizeof(request));request.bitmapcount=ATTR_BIT_MAP_COUNT;
    request.commonattr=ATTR_CMN_RETURNED_ATTRS;request.volattr=ATTR_VOL_INFO|ATTR_VOL_UUID;
    memset(raw,0,sizeof(raw));
    if(fgetattrlist(fd,&request,raw,sizeof(raw),0)!=0)return 0;
    memcpy(&length,raw,4);memcpy(masks,raw+4,20);
    if(length!=40 || masks[0]!=ATTR_CMN_RETURNED_ATTRS || masks[1]!=ATTR_VOL_UUID ||
       masks[2] || masks[3] || masks[4])return 0;
    unsigned any=0;for(int i=24;i<40;i++)any|=raw[i];if(!any)return 0;
    int used=0;for(int i=0;i<16;i++) {
        if(i==4 || i==6 || i==8 || i==10)volume[used++]='-';
        snprintf(volume+used,3,"%02x",raw[24+i]);used+=2;
    }
    return used==36;
}
static int current_boot_identity(char out[37]) {
    char raw[64];size_t size=sizeof(raw);
    if(sysctlbyname("kern.bootsessionuuid",raw,&size,NULL,0)!=0 || size!=37 || raw[36])return 0;
    for(int i=0;i<36;i++) {
        if(i==8 || i==13 || i==18 || i==23){if(raw[i]!='-')return 0;out[i]='-';}
        else if(raw[i]>='0'&&raw[i]<='9')out[i]=raw[i];
        else if(raw[i]>='a'&&raw[i]<='f')out[i]=raw[i];
        else if(raw[i]>='A'&&raw[i]<='F')out[i]=raw[i]-'A'+'a';else return 0;
    }
    out[36]=0;return 1;
}
static char operation_boot_identity[37];
static int operation_boot_bound(void) {
    char observed[37];if(!current_boot_identity(observed))return 0;
    if(!operation_boot_identity[0])strcpy(operation_boot_identity,observed);
    return !strcmp(operation_boot_identity,observed);
}
static const char *approved_persistent_binding = "{\"anchor_path\":\"/Users/imranali/Library/Application Support/KRONOS/runtime\",\"bundle_id\":\"com.project-kronos.browser-v1\",\"bundle_path\":\"/Applications/KRONOS.app\",\"enrollment\":{\"bytes\":355,\"identity\":\"5e6222c665fdb83f0750ff7ef4e0aa4c9423c8d82ece3554869d98817448aad6\",\"path\":\"/Users/imranali/Library/Application Support/KRONOS/runtime/e02-frozen-enrollment.json\",\"sha256\":\"f09519b6d460d2c5b6fe8405f0d0dc0beeff521ae5195fd9f9e023aa28afab8c\"},\"file_id\":694844364,\"installation_identity\":\"5e6222c665fdb83f0750ff7ef4e0aa4c9423c8d82ece3554869d98817448aad6\",\"owner\":501,\"repository_path\":\"/Users/imranali/Documents/GitHub/Project-Kronos\",\"required_mode\":\"0700\",\"schema\":\"KRONOS_PERSISTENT_ANCHOR_BINDING_V1\",\"volume_uuid\":\"ef7987a8-eb54-439a-8694-b1b1d87ead2c\"}";
static const char *approved_ordinary_restart_policy = NULL;
static int persistent_anchor_matches(int,const char *,dev_t,ino_t,uid_t);

static int open_admission_anchor(const char *path, dev_t device, ino_t inode, uid_t owner) {
    if (!path || path[0]!='/' || !device || !inode || owner!=getuid()) return -1;
    char copy[PATH_MAX];
    if (strlen(path)>=sizeof(copy)) return -1;
    strcpy(copy,path);
    int fd=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    if(fd<0)return -1;
    char *state=NULL;
    for(char *part=strtok_r(copy,"/",&state);part;part=strtok_r(NULL,"/",&state)) {
        if(!strcmp(part,".") || !strcmp(part,"..")){close(fd);return -1;}
        int next=openat(fd,part,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
        close(fd);if(next<0)return -1;fd=next;
        struct stat st;
        if(fstat(fd,&st)!=0 || (st.st_uid!=0 && st.st_uid!=owner) || (st.st_mode&0022)) {
            close(fd);return -1;
        }
    }
    struct stat st;
    if(fstat(fd,&st)!=0 || !S_ISDIR(st.st_mode) || st.st_uid!=owner ||
       (st.st_mode&0077) || st.st_ino!=inode ||
       (approved_persistent_binding ? !persistent_anchor_matches(fd,path,device,inode,owner) : st.st_dev!=device)) {close(fd);return -1;}
    return fd;
}

static int acquire_installation_admission(const char *path, dev_t device, ino_t inode) {
    int fd=open_admission_anchor(path,device,inode,getuid());
    if(fd<0)return -1;
    if(flock(fd,LOCK_EX|LOCK_NB)!=0){close(fd);return -1;}
    struct stat observed;if(fstat(fd,&observed)!=0){close(fd);return -1;}
    if(admission_descriptor<0){operation_observed_device=observed.st_dev;operation_observed_inode=observed.st_ino;}
    return fd;
}

/* Preserve the existing caller shape. Repository discovery is not lock-domain
 * selection: only the fixed installation path and approved binding are used. */
static int acquire_launcher_lock(const char *repository) {
    (void)repository;
    return acquire_installation_admission(admission_anchor,approved_admission_device,
                                          approved_admission_inode);
}

/* Helpers close all aliases before helper work, configuration, fork or exec.
 * This excludes custody; it is not descendant-termination proof (Slice 2.3). */
static void close_helper_admission(void) {
    struct stat held;
    if(admission_descriptor<0)return;
    if(fstat(admission_descriptor,&held)!=0)_exit(126);
    int maximum=getdtablesize();
    if(maximum<=0)_exit(126);
    for(int fd=3;fd<maximum;fd++) {
        struct stat st;
        if(fstat(fd,&st)==0) {
            if(st.st_dev==held.st_dev && st.st_ino==held.st_ino && close(fd)!=0)_exit(126);
        } else if(errno!=EBADF)_exit(126);
    }
    admission_descriptor=-1;
}

static int admission_still_bound(void) {
    if(admission_descriptor<0)return 0;
    int probe=open_admission_anchor(admission_anchor,approved_admission_device,
                                    approved_admission_inode,getuid());
    if(probe<0)return 0;
    struct stat original,current;
    int valid=fstat(admission_descriptor,&original)==0 && fstat(probe,&current)==0 &&
        original.st_dev==current.st_dev && original.st_ino==current.st_ino &&
        original.st_dev==operation_observed_device && original.st_ino==operation_observed_inode &&
        flock(admission_descriptor,LOCK_EX|LOCK_NB)==0;
    if(valid) {
        if(flock(probe,LOCK_EX|LOCK_NB)==0) valid=0;
        else if(errno!=EWOULDBLOCK && errno!=EAGAIN)valid=0;
    }
    close(probe);return valid;
}

static void validation_outcome(const char *,long long,pid_t,const char *,int);
static long long validation_current_deadline(void);
static int validation_has_unresolved(void);
static pid_t validation_owned_child(void);
static void reap_validation_child(void);
static void finish_admission(void) {
    if(admission_child>0 && !admission_ready) {
        if(!admission_child_observed) {
            pid_t observed=waitpid(admission_child,&admission_child_status,WNOHANG);
            admission_child_observed=observed==admission_child;
        }
        if(!admission_child_observed || !WIFEXITED(admission_child_status) ||
           WEXITSTATUS(admission_child_status)!=ADMISSION_CLEANUP_COMPLETE_EXIT) {
            validation_outcome("BACKEND_STARTUP",validation_current_deadline(),admission_child,
                               "STARTUP_NOT_ACCEPTED",1);
            for(;;) {
                if(!admission_child_observed) {
                    pid_t observed=waitpid(admission_child,&admission_child_status,WNOHANG);
                    admission_child_observed=observed==admission_child;
                }
                if(admission_child_observed && WIFEXITED(admission_child_status) &&
                   WEXITSTATUS(admission_child_status)==ADMISSION_CLEANUP_COMPLETE_EXIT &&
                   !validation_has_unresolved() &&
                   (!native_startup_active() || native_terminal_cleanup()))break;
                reap_validation_child();
                usleep(100000); /* Custody retention only: never a renewed decision. */
            }
        }
    }
    if(admission_child>0 && !admission_ready && native_startup_active() && !native_terminal_cleanup()) {
        validation_outcome("NATIVE_TERMINAL",validation_current_deadline(),admission_child,
                           "ACTUAL_CHILD_FACTS_UNRESOLVED",1);
        for(;;){reap_validation_child();usleep(100000);}
    }
    if(validation_has_unresolved()) {
        validation_outcome("VALIDATION",validation_current_deadline(),validation_owned_child(),
                           "HELPER_OUTCOME_UNRESOLVED",1);
        for(;;){reap_validation_child();usleep(100000);}
    }
    if(admission_descriptor>=0){close(admission_descriptor);admission_descriptor=-1;}
}

static long long validation_deadline_ns=0,stop_deadline_ns=0,handoff_deadline_ns=0,backend_ready_deadline_ns=0;
static int validation_failed=0,validation_cleanup_unresolved=0;
static pid_t validation_direct_child=0;
static const char *validation_phase="PRE_TRANSITION";
static long long validation_current_deadline(void){return backend_ready_deadline_ns?backend_ready_deadline_ns:validation_deadline_ns;}
static int validation_has_unresolved(void){return validation_cleanup_unresolved;}
static pid_t validation_owned_child(void){return validation_direct_child;}
static void reap_validation_child(void) {
    static int terminal_observed=0;
    if(validation_direct_child>0 && !terminal_observed) {
        int status;pid_t observed=waitpid(validation_direct_child,&status,WNOHANG);
        if(observed==validation_direct_child || (observed<0 && errno==ECHILD)) {
            terminal_observed=1;
            validation_outcome("VALIDATION_CLEANUP",validation_deadline_ns,validation_direct_child,
                observed>0?"DIRECT_CHILD_REAPED":"DIRECT_CHILD_NO_LONGER_WAITABLE",1);
        }
    }
}



static long long validation_now_ns(void) {
    struct timespec now;if(clock_gettime(CLOCK_MONOTONIC,&now)!=0)return 0;
    return (long long)now.tv_sec*1000000000LL+now.tv_nsec;
}
static int validation_permitted(void) {
    long long now=validation_now_ns();
    if(validation_failed || validation_cleanup_unresolved || !operation_boot_bound() || !now ||
       (validation_deadline_ns && now>=validation_deadline_ns)) {
        validation_failed=1;return 0;
    }
    return 1;
}
static void validation_outcome(const char *phase,long long deadline,pid_t child,const char *result,int unresolved) {
    char raw[512];int n=snprintf(raw,sizeof(raw),
        "{\"schema\":\"KRONOS_VALIDATION_OUTCOME_V1\",\"phase\":\"%s\",\"clock\":\"CLOCK_MONOTONIC\",\"deadline_ns\":%lld,\"direct_child\":%ld,\"observed_result\":\"%s\",\"cleanup\":\"%s\"}\n",
        phase,deadline,(long)child,result,unresolved?"CLEANUP_UNRESOLVED":child>0?"DIRECT_CHILD_OBSERVED":"NOT_STARTED");
    if(n<0 || n>=(int)sizeof(raw)){validation_cleanup_unresolved=1;return;}
    struct sigaction ignore={0},previous={0};ignore.sa_handler=SIG_IGN;sigemptyset(&ignore.sa_mask);
    if(sigaction(SIGPIPE,&ignore,&previous)!=0){validation_cleanup_unresolved=1;return;}
    int flags=fcntl(STDERR_FILENO,F_GETFL);
    if(flags>=0 && fcntl(STDERR_FILENO,F_SETFL,flags|O_NONBLOCK)==0) {
        if(write(STDERR_FILENO,raw,(size_t)n)!=n)validation_cleanup_unresolved=1;
        /* Keep shared startup output nonblocking; no stale flags restore. */
    } else validation_cleanup_unresolved=1;
    if(sigaction(SIGPIPE,&previous,NULL)!=0)validation_cleanup_unresolved=1;
}
static int validation_environment_key(const char *entry) {
    const char *equal=strchr(entry,'=');if(!equal)return 0;
    size_t n=(size_t)(equal-entry);
    const char *keys[]={"PATH","HOME","XDG_CONFIG_HOME","SSH_AUTH_SOCK","SSH_AGENT_PID",
        "SSH_ASKPASS","SSH_ASKPASS_REQUIRE","SSH_SK_PROVIDER","DISPLAY","XAUTHORITY","TERM","LANG","TMPDIR","USER","LOGNAME",
        "DEVELOPER_DIR","KRB5CCNAME","KRB5_CONFIG","KRB5_KTNAME",
        "SHELL","PYTHONPATH","PYTHONDONTWRITEBYTECODE","__CF_USER_TEXT_ENCODING",NULL};
    if((n>=4 && !strncmp(entry,"GIT_",4)) || (n>=3 && !strncmp(entry,"LC_",3)))return 1;
    for(int i=0;keys[i];i++)if(strlen(keys[i])==n && !strncmp(entry,keys[i],n))return 1;
    return 0;
}
static int validation_child_environment(const char *repository,long long deadline) {
    extern char **environ;
    static char *clean[512];int used=0;
    for(char **p=environ;*p;p++)if(validation_environment_key(*p)) {
        if(used>=508)return 0;clean[used++]=*p;
    }
    clean[used]=NULL;environ=clean;
    char number[32],path[PATH_MAX*2];
    if(snprintf(number,sizeof(number),"%lld",deadline)>=(int)sizeof(number) ||
       setenv("KRONOS_VALIDATION_CLOCK","CLOCK_MONOTONIC",1)!=0 ||
       setenv("KRONOS_VALIDATION_DEADLINE_NS",number,1)!=0 || !operation_boot_bound() ||
       setenv("KRONOS_VALIDATION_BOOT_SESSION",operation_boot_identity,1)!=0)return 0;
    if(repository && (chdir(repository)!=0 ||
       snprintf(path,sizeof(path),"%s/src:%s",repository,repository)>=(int)sizeof(path) ||
       setenv("PYTHONPATH",path,1)!=0))return 0;
    return 1;
}
static int bounded_validation_cli(const char *repository,const char *executable,char *const arguments[],
    const char *input,char *output,size_t capacity,int expected_exit,const char *phase,int ceiling) {
    long long started=validation_now_ns();
    long long deadline=started+(long long)ceiling*1000000000LL;
    if(!started || ceiling<1 || capacity<2 || !validation_permitted()) {
        validation_outcome(phase,validation_deadline_ns,0,"NOT_STARTED_DEADLINE",0);return 0;
    }
    if(validation_deadline_ns && validation_deadline_ns<deadline)deadline=validation_deadline_ns;
    struct sigaction child_signal;
    if(sigaction(SIGCHLD,NULL,&child_signal)!=0 || child_signal.sa_handler!=SIG_DFL ||
       (child_signal.sa_flags&SA_NOCLDWAIT)) {
        validation_failed=1;validation_cleanup_unresolved=1;
        validation_outcome(phase,deadline,0,"CHILD_OWNERSHIP_NOT_ESTABLISHED",1);return 0;
    }
    int in[2],out[2];
    if(pipe(in)!=0){validation_failed=1;validation_outcome(phase,deadline,0,"PIPE_FAILURE",0);return 0;}
    if(pipe(out)!=0){close(in[0]);close(in[1]);validation_failed=1;validation_outcome(phase,deadline,0,"PIPE_FAILURE",0);return 0;}
    pid_t child=fork();
    if(child<0){close(in[0]);close(in[1]);close(out[0]);close(out[1]);validation_failed=1;validation_outcome(phase,deadline,0,"FORK_FAILURE",0);return 0;}
    if(child==0) {
        close_helper_admission();
        if(!validation_child_environment(repository,deadline) ||
           dup2(in[0],STDIN_FILENO)<0 || dup2(out[1],STDOUT_FILENO)<0 || dup2(out[1],STDERR_FILENO)<0)_exit(125);
        close(in[0]);close(in[1]);close(out[0]);close(out[1]);
        execv(executable,arguments);_exit(125);
    }
    validation_direct_child=child;close(in[0]);close(out[1]);
    struct sigaction ignore={0},previous={0};ignore.sa_handler=SIG_IGN;sigemptyset(&ignore.sa_mask);
    int installed=sigaction(SIGPIPE,&ignore,&previous)==0;
    int ok=installed && fcntl(in[1],F_SETFL,O_NONBLOCK)==0 && fcntl(out[0],F_SETFL,O_NONBLOCK)==0;
    size_t sent=0,length=input?strlen(input):0,used=0;
    int writing=1,reading=1,observed=0,status=0;
    const char *result="IO_FAILURE";
    if(!length){close(in[1]);writing=0;}
    while(ok && (writing || reading || !observed)) {
        long long now=validation_now_ns();
        if(!now || now>=deadline){result="DEADLINE_EXPIRED";ok=0;break;}
        struct pollfd descriptors[2]={{writing?in[1]:-1,POLLOUT,0},{reading?out[0]:-1,POLLIN,0}};
        long long remaining=(deadline-now+999999LL)/1000000LL;
        int wait=remaining>20?20:(int)remaining;
        int polled=poll(descriptors,2,wait);
        if(polled<0){
            if(errno!=EINTR){ok=0;break;}
            polled=0; /* Still observe/reap the child under repeated signals. */
        }
        if(writing && descriptors[0].revents) {
            ssize_t n=write(in[1],input+sent,length-sent);
            if(n>0){sent+=(size_t)n;if(sent==length){close(in[1]);writing=0;}}
            else if(n<0 && errno!=EINTR && errno!=EAGAIN){ok=0;break;}
        }
        if(reading && descriptors[1].revents) {
            char extra;ssize_t n=used+1<capacity?read(out[0],output+used,capacity-1-used):read(out[0],&extra,1);
            if(n==0){close(out[0]);reading=0;}
            else if(n>0){if(used+1>=capacity){result="OUTPUT_LIMIT";ok=0;break;}used+=(size_t)n;}
            else if(errno!=EINTR && errno!=EAGAIN){ok=0;break;}
        }
        if(!observed) {
            pid_t found=waitpid(child,&status,WNOHANG);
            if(found==child)observed=1;
            else if(found<0 && errno!=EINTR){result="WAIT_UNRESOLVED";ok=0;break;}
        }
    }
    if(writing)close(in[1]);if(reading)close(out[0]);
    if(installed && sigaction(SIGPIPE,&previous,NULL)!=0){ok=0;result="SIGNAL_RESTORE_FAILURE";}
    if(memchr(output,0,used)){result="OUTPUT_INVALID";ok=0;}output[used]=0;
    long long finished=validation_now_ns();
    if(!finished || finished>=deadline){result="LATE_RESULT";ok=0;}
    if(ok && observed && WIFEXITED(status) && WEXITSTATUS(status)==expected_exit) {
        validation_direct_child=0;return 1;
    }
    validation_failed=1;
    if(!observed) {
        /* Only the exact directly owned validation child; never groups/products. */
        pid_t found=waitpid(child,&status,WNOHANG);
        if(found==0) {
            /* SIGCHLD default/no-autoreap plus this unreaped direct-child wait
             * result prevents PID reuse while the signal is issued. */
            (void)kill(child,SIGKILL);
            found=waitpid(child,&status,WNOHANG);
        }
        observed=found==child;
        validation_cleanup_unresolved=1;
    }
    if(!strcmp(result,"LATE_RESULT") || !strcmp(result,"DEADLINE_EXPIRED") ||
       !strcmp(result,"OUTPUT_LIMIT") || (observed && WIFEXITED(status) && WEXITSTATUS(status)==79))
        validation_cleanup_unresolved=1;
    if(observed && ok)result="DIRECT_CHILD_FAILURE";
    validation_outcome(phase?phase:validation_phase,deadline,child,result,validation_cleanup_unresolved);
    if(observed && !validation_cleanup_unresolved)validation_direct_child=0;
    return 0;
}
static int canonical_image_path(const char *image) {
    char resolved_image[PATH_MAX];
    char resolved_canonical[PATH_MAX];
    struct stat metadata;
    if (image == NULL || realpath(image, resolved_image) == NULL ||
        realpath(canonical_executable, resolved_canonical) == NULL ||
        strcmp(resolved_canonical, canonical_executable) != 0 ||
        strcmp(resolved_image, canonical_executable) != 0 ||
        stat(resolved_image, &metadata) != 0 || !S_ISREG(metadata.st_mode)) return 0;
    return 1;
}

static int canonical_signature_valid(void) {
    char output[4096]={0};
    char *arguments[]={"codesign","--verify","--deep","--strict","-R",
        "=identifier \"com.project-kronos.browser-v1\"",(char*)canonical_bundle,NULL};
    return bounded_validation_cli(NULL,"/usr/bin/codesign",arguments,NULL,output,sizeof(output),0,
                                  "NATIVE_SIGNATURE",10);
}

static int canonical_operational_image(void) {
    char image[PATH_MAX];
    uint32_t capacity = sizeof(image);
    return _NSGetExecutablePath(image, &capacity) == 0 &&
        canonical_image_path(image) && canonical_signature_valid();
}

static const char *workspace_script =
    "tell application \"Google Chrome\"\n"
    "repeat with browserWindow in windows\n"
    "set tabNumber to 0\n"
    "repeat with browserTab in tabs of browserWindow\n"
    "set tabNumber to tabNumber + 1\n"
    "if URL of browserTab starts with \"http://127.0.0.1:8947/\" then\n"
    "set active tab index of browserWindow to tabNumber\n"
    "set index of browserWindow to 1\n"
    "activate\n"
    "if URL of browserTab is \"http://127.0.0.1:8947/swing/opportunities\" then "
    "set URL of browserTab to \"http://127.0.0.1:8947/swing/opportunities\"\n"
    "return\n"
    "end if\n"
    "end repeat\n"
    "end repeat\n"
    "open location \"http://127.0.0.1:8947/swing/opportunities\"\n"
    "activate\n"
    "end tell";
static const char *control_schema = "KRONOS_BROWSER_BACKEND_CONTROL_V1";
#define BACKEND_STATUS_RESPONSE_BYTES (64 * 1024)
#define HANDOFF_SECONDS 45
/* Non-null only while monitoring an explicitly authorized recovery successor. */
static const struct timespec *recovery_io_deadline=NULL;

static int recovery_wait_io(int fd,short events,const struct timespec *deadline) {
    for(;;){
        struct timespec now;if(clock_gettime(CLOCK_MONOTONIC,&now)!=0)return 0;
        long long remaining=(long long)(deadline->tv_sec-now.tv_sec)*1000000000LL+deadline->tv_nsec-now.tv_nsec;
        if(remaining<=0)return 0;
        long long milliseconds=(remaining+999999)/1000000;
        struct pollfd item={.fd=fd,.events=events};
        int result=poll(&item,1,milliseconds>INT_MAX?INT_MAX:(int)milliseconds);
        if(result<0&&errno==EINTR)continue;
        return result>0 && !(item.revents&POLLNVAL);
    }
}

static int directory_exists(const char *path) {
    struct stat metadata;
    return stat(path, &metadata) == 0 && S_ISDIR(metadata.st_mode);
}

static int repository_is_governed(const char *repository) {
    char git_directory[PATH_MAX];
    char project_file[PATH_MAX];
    char python[PATH_MAX];
    char browser_entry[PATH_MAX];
    char package_directory[PATH_MAX];
    if (
        snprintf(git_directory, sizeof(git_directory), "%s/.git", repository) < 0 ||
        snprintf(project_file, sizeof(project_file), "%s/pyproject.toml", repository) < 0 ||
        snprintf(python, sizeof(python), "%s/.venv/bin/python", repository) < 0 ||
        snprintf(browser_entry, sizeof(browser_entry), "%s/tools/kronos_browser.py", repository) < 0 ||
        snprintf(package_directory, sizeof(package_directory), "%s/src/kronos", repository) < 0
    ) {
        return 0;
    }
    return (
        directory_exists(git_directory) &&
        access(project_file, R_OK) == 0 &&
        access(python, X_OK) == 0 &&
        access(browser_entry, R_OK) == 0 &&
        directory_exists(package_directory)
    );
}

static int discover_repository(const char *home, char repository[PATH_MAX]) {
    static const char *relative_roots[] = {
        "Documents/GitHub",
        "Developer",
        "Projects",
    };
    int matches = 0;
    for (size_t root_index = 0;
         root_index < sizeof(relative_roots) / sizeof(relative_roots[0]);
         ++root_index) {
        char root[PATH_MAX];
        if (snprintf(root, sizeof(root), "%s/%s", home, relative_roots[root_index]) < 0) {
            return 0;
        }
        DIR *directory = opendir(root);
        if (directory == NULL) continue;
        struct dirent *entry = NULL;
        while ((entry = readdir(directory)) != NULL) {
            if (entry->d_name[0] == '.') continue;
            char candidate[PATH_MAX];
            int length = snprintf(candidate, sizeof(candidate), "%s/%s", root, entry->d_name);
            if (
                length < 1 ||
                (size_t)length >= sizeof(candidate) ||
                !repository_is_governed(candidate)
            ) {
                continue;
            }
            ++matches;
            if (matches == 1) {
                (void)memcpy(repository, candidate, (size_t)length + 1);
            }
        }
        (void)closedir(directory);
    }
    return matches == 1;
}

static int connect_backend(void) {
    int socket_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (socket_fd < 0) return -1;

    struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
    (void)setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    (void)setsockopt(socket_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(8947);
    int flags=fcntl(socket_fd,F_GETFL);
    if(recovery_io_deadline && (flags<0 || fcntl(socket_fd,F_SETFL,flags|O_NONBLOCK)!=0)) {
        close(socket_fd);return -1;
    }
    if(inet_pton(AF_INET,"127.0.0.1",&address.sin_addr)!=1){close(socket_fd);return -1;}
    int connected=connect(socket_fd,(struct sockaddr *)&address,sizeof(address));
    if(connected!=0) {
        if(!recovery_io_deadline || (errno!=EINPROGRESS && errno!=EINTR) ||
           !recovery_wait_io(socket_fd,POLLOUT,recovery_io_deadline)) {close(socket_fd);return -1;}
        int error=0;socklen_t size=sizeof(error);
        if(getsockopt(socket_fd,SOL_SOCKET,SO_ERROR,&error,&size)!=0 || error) {close(socket_fd);return -1;}
    }
    if(recovery_io_deadline) {
        struct timespec now;if(clock_gettime(CLOCK_MONOTONIC,&now)!=0){close(socket_fd);return -1;}
        long long remaining=(long long)(recovery_io_deadline->tv_sec-now.tv_sec)*1000000000LL+
            recovery_io_deadline->tv_nsec-now.tv_nsec;
        if(remaining<=0 || fcntl(socket_fd,F_SETFL,flags)!=0){close(socket_fd);return -1;}
        if(remaining<1000000000LL) {
            struct timeval bound={.tv_sec=0,.tv_usec=(suseconds_t)((remaining+999)/1000)};
            (void)setsockopt(socket_fd,SOL_SOCKET,SO_RCVTIMEO,&bound,sizeof(bound));
            (void)setsockopt(socket_fd,SOL_SOCKET,SO_SNDTIMEO,&bound,sizeof(bound));
        }
    }
    return socket_fd;
}

static int read_response(int socket_fd, char *response, size_t capacity) {
    if (capacity < 2) return -1;
    size_t used = 0;
    int closed = 0;
    while (used < capacity - 1) {
        if(recovery_io_deadline && !recovery_wait_io(socket_fd,POLLIN,recovery_io_deadline))return -1;
        ssize_t received = recv(socket_fd, response + used, capacity - 1 - used, 0);
        if (received == 0) {
            closed = 1;
            break;
        }
        if (received < 0) {
            if (errno == EINTR) continue;
            response[0] = '\0';
            return -1;
        }
        used += (size_t)received;
    }
    if (!closed) {
        char extra = '\0';
        for (;;) {
            if(recovery_io_deadline && !recovery_wait_io(socket_fd,POLLIN,recovery_io_deadline))return -1;
            ssize_t received = recv(socket_fd, &extra, sizeof(extra), 0);
            if (received == 0) break;
            if (received > 0) {
                response[0] = '\0';
                return -1;
            }
            if (errno == EINTR) continue;
            response[0] = '\0';
            return -1;
        }
    }
    response[used] = '\0';
    if (used == 0 || memchr(response, '\0', used) != NULL) {
        response[0] = '\0';
        return -1;
    }
    const char *header_end = strstr(response, "\r\n\r\n");
    const char *line_end = strstr(response, "\r\n");
    if (header_end == NULL || line_end == NULL || line_end >= header_end) {
        response[0] = '\0';
        return -1;
    }
    size_t header_bytes = (size_t)(header_end + 4 - response);
    const char *line = line_end + 2;
    int content_length_found = 0;
    size_t content_length = 0;
    while (line < header_end) {
        line_end = strstr(line, "\r\n");
        if (line_end == NULL || line_end > header_end) {
            response[0] = '\0';
            return -1;
        }
        if ((size_t)(line_end - line) >= 15 &&
            strncmp(line, "Content-Length:", 15) == 0) {
            if (content_length_found) {
                response[0] = '\0';
                return -1;
            }
            const char *value = line + 15;
            while (value < line_end && (*value == ' ' || *value == '\t')) ++value;
            const char *first_digit = value;
            while (value < line_end && *value >= '0' && *value <= '9') {
                size_t digit = (size_t)(*value - '0');
                if (content_length > (((size_t)-1) - digit) / 10) {
                    response[0] = '\0';
                    return -1;
                }
                content_length = content_length * 10 + digit;
                ++value;
            }
            while (value < line_end && (*value == ' ' || *value == '\t')) ++value;
            if (value == first_digit || value != line_end) {
                response[0] = '\0';
                return -1;
            }
            content_length_found = 1;
        }
        line = line_end + 2;
    }
    if (!content_length_found || header_bytes > used ||
        content_length != used - header_bytes) {
        response[0] = '\0';
        return -1;
    }
    return (int)used;
}

static int response_is_ready(const char *response) {
    return (
        strncmp(response, "HTTP/1.0 200 ", 13) == 0 &&
        strstr(response, "\"service\":\"KRONOS_BROWSER_V1\"") != NULL &&
        strstr(response, "\"provider\"") != NULL &&
        strstr(response, "\"analysis\"") != NULL &&
        strstr(response, "\"runtime_ready\":true") != NULL
    );
}

static int backend_is_ready(void) {
    int socket_fd = connect_backend();
    if (socket_fd < 0) return 0;
    static const char request[] =
        "GET /status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n";
    if (send(socket_fd, request, sizeof(request) - 1, 0) != (ssize_t)(sizeof(request) - 1)) {
        (void)close(socket_fd);
        return 0;
    }
    char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    int response_bytes = read_response(socket_fd, response, sizeof(response));
    (void)close(socket_fd);
    return response_bytes > 0 && response_is_ready(response);
}

static int open_workspace(void) {
    finish_admission();
    execl(
        "/usr/bin/osascript",
        "osascript",
        "-e",
        workspace_script,
        (char *)NULL
    );
    return 1;
}

static int show_alert(const char *title, const char *message) {
    finish_admission();
    char script[768];
    if (
        snprintf(
            script,
            sizeof(script),
            "display alert \"%s\" message \"%s\" as critical",
            title,
            message
        ) < 0
    ) {
        return 1;
    }
    execl("/usr/bin/osascript", "osascript", "-e", script, (char *)NULL);
    return 1;
}

static int show_not_ready(void) {
    return show_alert(
        "KRONOS is not ready",
        "The approved local Python environment was not found. Contact Engineering."
    );
}

static int show_restart_blocked(void) {
    return show_alert(
        "KRONOS restart blocked",
        "The existing KRONOS backend could not be stopped through the authenticated maintenance handoff. No replacement was started. Contact Engineering."
    );
}

static int show_existing_backend_unhealthy(void) {
    return show_alert(
        "KRONOS is not ready",
        "A KRONOS backend already owns the local Browser address but is not ready. It was not restarted. Contact Engineering."
    );
}

static int show_replacement_child_exited(void) {
    return show_alert(
        "KRONOS replacement failed",
        "The previous backend stopped safely, but the replacement process exited before becoming ready. Do not relaunch KRONOS. Contact Engineering."
    );
}

static int show_replacement_ready_timeout(void) {
    return show_alert(
        "KRONOS is still starting",
        "The previous backend stopped safely and the replacement was started, but it did not become ready within 120 seconds. Do not relaunch KRONOS. Contact Engineering."
    );
}

static int show_replacement_internal_failure(void) {
    return show_alert(
        "KRONOS replacement failed",
        "The previous backend stopped safely, but the replacement could not be started or monitored safely. Do not relaunch KRONOS. Contact Engineering."
    );
}

static int valid_token(const char *token) {
    if (strlen(token) != 64) return 0;
    for (size_t index = 0; index < 64; ++index) {
        char value = token[index];
        if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f'))) {
            return 0;
        }
    }
    return 1;
}

static int valid_revision(const char *revision) {
    if (revision == NULL || strlen(revision) != 40) return 0;
    for (size_t index = 0; index < 40; ++index) {
        char value = revision[index];
        if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f'))) {
            return 0;
        }
    }
    return 1;
}

static int repository_revision_matches(const char *repository,const char *expected) {
    if(!valid_revision(expected))return 0;
    char output[42]={0};char *arguments[]={"git","rev-parse","HEAD",NULL};
    return bounded_validation_cli(repository,"/usr/bin/git",arguments,NULL,output,sizeof(output),0,
        "LOCAL_REVISION",10) && strlen(output)==41 && output[40]=='\n' && memcmp(output,expected,40)==0;
}

static int read_control_record(
    const char *control_path,
    pid_t *backend_pid,
    char token[65]
) {
    FILE *handle = fopen(control_path, "r");
    if (handle == NULL) return 0;
    struct stat metadata;
    if (
        fstat(fileno(handle), &metadata) != 0 ||
        !S_ISREG(metadata.st_mode) ||
        metadata.st_uid != getuid() ||
        (metadata.st_mode & 077) != 0
    ) {
        (void)fclose(handle);
        return 0;
    }
    char schema[64] = {0};
    char pid_line[32] = {0};
    char token_line[80] = {0};
    int read_ok = (
        fgets(schema, sizeof(schema), handle) != NULL &&
        fgets(pid_line, sizeof(pid_line), handle) != NULL &&
        fgets(token_line, sizeof(token_line), handle) != NULL
    );
    (void)fclose(handle);
    if (!read_ok) return 0;
    schema[strcspn(schema, "\r\n")] = '\0';
    pid_line[strcspn(pid_line, "\r\n")] = '\0';
    token_line[strcspn(token_line, "\r\n")] = '\0';
    char *end = NULL;
    errno = 0;
    long parsed_pid = strtol(pid_line, &end, 10);
    if (
        strcmp(schema, control_schema) != 0 ||
        errno != 0 ||
        end == pid_line ||
        *end != '\0' ||
        parsed_pid < 2 ||
        parsed_pid > INT_MAX ||
        !valid_token(token_line)
    ) {
        return 0;
    }
    *backend_pid = (pid_t)parsed_pid;
    (void)memcpy(token, token_line, 65);
    return 1;
}

static int backend_is_reusable(const char *control_path) {
    if (!backend_is_ready()) return 0;
    pid_t backend_pid = 0;
    char token[65] = {0};
    int reusable = (
        read_control_record(control_path, &backend_pid, token) &&
        kill(backend_pid, 0) == 0
    );
    (void)memset(token, 0, sizeof(token));
    return reusable;
}

typedef enum ReplacementReadiness {
    REPLACEMENT_NOT_READY,
    REPLACEMENT_REQUIRED,
    REPLACEMENT_REQUIRED_OLD_CF55,
    REPLACEMENT_ALREADY_LOADED,
} ReplacementReadiness;

static const char *old_runtime_compatibility_revision =
    "cf55fa827b33d27ec44efb8988d413b1088ae07d";

static int read_backend_route(
    const char *path,
    char response[BACKEND_STATUS_RESPONSE_BYTES]
) {
    int socket_fd = connect_backend();
    if (socket_fd < 0) return 0;
    char request[160];
    int request_bytes = snprintf(
        request,
        sizeof(request),
        "GET %s HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n",
        path
    );
    if (
        request_bytes < 1 ||
        (size_t)request_bytes >= sizeof(request) ||
        send(socket_fd, request, (size_t)request_bytes, 0) != request_bytes
    ) {
        (void)close(socket_fd);
        return 0;
    }
    int response_bytes = read_response(
        socket_fd,
        response,
        BACKEND_STATUS_RESPONSE_BYTES
    );
    (void)close(socket_fd);
    return response_bytes > 0 && strncmp(response, "HTTP/1.0 200 ", 13) == 0;
}

static int response_has_all(
    const char *response,
    const char *const required[],
    size_t count
) {
    for (size_t index = 0; index < count; ++index) {
        if (strstr(response, required[index]) == NULL) return 0;
    }
    return 1;
}

static int runtime_process_revision(
    const char *response,
    pid_t backend_pid,
    char revision[41]
) {
    char process_marker[96];
    int marker_bytes = snprintf(
        process_marker,
        sizeof(process_marker),
        "\"process\":{\"pid\":%ld,\"revision\":\"",
        (long)backend_pid
    );
    if (marker_bytes < 1 || (size_t)marker_bytes >= sizeof(process_marker)) return 0;
    const char *loaded = strstr(response, process_marker);
    if (loaded == NULL) return 0;
    loaded += (size_t)marker_bytes;
    if (strlen(loaded) < 41) return 0;
    (void)memcpy(revision, loaded, 40);
    revision[40] = '\0';
    return valid_revision(revision) && loaded[40] == '"';
}

static int maintenance_generation(const char *response, char generation[65]) {
    static const char marker[] =
        "\"maintenance\":{\"protocol\":\"KRONOS_MAINTENANCE_HANDOFF_V1\","
        "\"state\":\"INACTIVE\",\"active\":false,\"generation\":\"";
    const char *value = strstr(response, marker);
    if (value == NULL) return 0;
    value += sizeof(marker) - 1;
    if (strlen(value) < 65) return 0;
    (void)memcpy(generation, value, 64);
    generation[64] = '\0';
    return valid_token(generation) && value[64] == '"';
}

static int connection_is_quiescent(const char *response) {
    int connected = strstr(response, "\"rest_authentication\":\"CONNECTED\"") != NULL;
    int disconnected = strstr(response, "\"rest_authentication\":\"DISCONNECTED\"") != NULL;
    if ((!connected && !disconnected) || (connected && disconnected)) return 0;
    if (connected) {
        return
            strstr(response, "\"worker_active\":false,\"resources_pending\":false,\"cleanup_state\":\"COMPLETE\"") != NULL &&
            strstr(response, "\"restoration_worker_active\":false") != NULL;
    }
    return strstr(response, "\"connection_attempt\":null") != NULL;
}

static int runtime_shared_work_is_idle(const char *response) {
    static const char *required[] = {
        "\"startup\":\"READY\",\"failure\":null",
        "\"monitoring\":{\"schema\":\"KRONOS-SHARED-MONITORING-STATUS/1.0.0\",\"hub_state\":\"IDLE\",\"transport_state\":\"IDLE\",\"session_count\":0,\"active_session_count\":0,\"owner_count\":0,\"subscription_count\":0",
        "\"intraday_wo11_work\":{\"state\":\"IDLE\",\"generation\":null,\"owned_workers\":0",
        "\"intraday_wo17_work\":{\"state\":\"IDLE\",\"generation\":null,\"owned_workers\":0",
        "\"lifecycle_state\":\"IDLE\",\"shutdown_requested\":false,\"owned_workers\":0,\"worker_generation\":null,\"pass_active\":false",
        "\"swing_bulk_import\":{\"state\":\"IDLE\"",
        "\"batch_active\":false",
    };
    return response_has_all(response, required, sizeof(required) / sizeof(required[0])) &&
        connection_is_quiescent(response);
}

static int new_runtime_is_drainable(const char *response) {
    static const char *required[] = {
        "\"maintenance_drain\":{\"state\":\"OPEN\",\"generation\":null,\"owners\":",
        "\"maintenance_claim\":\"DRAINABLE\"",
        "\"startup\":\"READY\",\"failure\":null",
    };
    return response_has_all(response, required, sizeof(required) / sizeof(required[0]));
}

static int old_status_analysis_is_idle(const char *response) {
    static const char *required[] = {
        "\"service\":\"KRONOS_BROWSER_V1\"",
        "\"analysis\":\"READY\"",
        "\"swing_publication\":{\"control\":" ,
        "\"analysis_work\":{\"state\":\"IDLE\",\"generation\":null,\"run_identity\":null,\"owned_work_count\":0",
        "\"analysis_execution\":{\"state\":\"IDLE\",\"pid\":null,\"generation\":null,\"failure\":null,\"failure_diagnostic\":null,\"owned_workers\":0",
        "\"runtime_ready\":true",
        "\"intraday_wo11_work\":{\"state\":\"IDLE\",\"generation\":null,\"owned_workers\":0",
        "\"intraday_wo17_work\":{\"state\":\"IDLE\",\"generation\":null,\"owned_workers\":0",
        "\"lifecycle_state\":\"IDLE\",\"shutdown_requested\":false,\"owned_workers\":0,\"worker_generation\":null,\"pass_active\":false",
        "\"swing_bulk_import\":{\"state\":\"IDLE\"",
        "\"batch_active\":false",
    };
    return response_has_all(response, required, sizeof(required) / sizeof(required[0]));
}

static ReplacementReadiness backend_replacement_readiness(
    pid_t backend_pid,
    const char *target_revision
) {
    if (backend_pid < 2 || !valid_revision(target_revision) || kill(backend_pid, 0) != 0) {
        return REPLACEMENT_NOT_READY;
    }
    char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    char loaded_revision[41] = {0};
    if (
        !read_backend_route("/runtime/status", response) ||
        !runtime_process_revision(response, backend_pid, loaded_revision)
    ) {
        return REPLACEMENT_NOT_READY;
    }
    if (strcmp(loaded_revision, target_revision) == 0) {
        return REPLACEMENT_ALREADY_LOADED;
    }
    if (new_runtime_is_drainable(response)) return REPLACEMENT_REQUIRED;
    if (!runtime_shared_work_is_idle(response)) return REPLACEMENT_NOT_READY;
    if (strcmp(loaded_revision, old_runtime_compatibility_revision) != 0) {
        return REPLACEMENT_NOT_READY;
    }

    char first_generation[65] = {0};
    if (!maintenance_generation(response, first_generation)) return REPLACEMENT_NOT_READY;
    char status_response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    char status_generation[65] = {0};
    if (
        !read_backend_route("/status", status_response) ||
        !old_status_analysis_is_idle(status_response) ||
        !maintenance_generation(status_response, status_generation) ||
        strcmp(first_generation, status_generation) != 0
    ) {
        return REPLACEMENT_NOT_READY;
    }

    char recheck[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    char recheck_revision[41] = {0};
    char recheck_generation[65] = {0};
    if (
        !read_backend_route("/runtime/status", recheck) ||
        !runtime_process_revision(recheck, backend_pid, recheck_revision) ||
        strcmp(recheck_revision, loaded_revision) != 0 ||
        !runtime_shared_work_is_idle(recheck) ||
        new_runtime_is_drainable(recheck) ||
        !maintenance_generation(recheck, recheck_generation) ||
        strcmp(first_generation, recheck_generation) != 0
    ) {
        return REPLACEMENT_NOT_READY;
    }
    return REPLACEMENT_REQUIRED_OLD_CF55;
}

static int backend_supports_maintenance(void) {
    int socket_fd = connect_backend();
    if (socket_fd < 0) return 0;
    static const char request[] =
        "GET /status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n";
    if (send(socket_fd, request, sizeof(request) - 1, 0) != (ssize_t)(sizeof(request) - 1)) {
        (void)close(socket_fd);
        return 0;
    }
    char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    int response_bytes = read_response(socket_fd, response, sizeof(response));
    (void)close(socket_fd);
    return response_bytes > 0 &&
        strncmp(response, "HTTP/1.0 200 ", 13) == 0 &&
        strstr(response, "\"protocol\":\"KRONOS_MAINTENANCE_HANDOFF_V1\"") != NULL;
}

static int request_graceful_shutdown_effect(pid_t backend_pid, const char *token,
                                     const char *generation, int require_v2) {
    int socket_fd = connect_backend();
    if (socket_fd < 0) return 0;
    char request[1100];
    int length = snprintf(
        request,
        sizeof(request),
        "POST /control/shutdown HTTP/1.0\r\n"
        "Host: 127.0.0.1:8947\r\n"
        "X-Kronos-Backend-Pid: %ld\r\n"
        "X-Kronos-Restart-Token: %s\r\n"
        "X-Kronos-Maintenance-Generation: %s\r\n"
        "%s"
        "Content-Length: 0\r\n"
        "Connection: close\r\n\r\n",
        (long)backend_pid,
        token,
        generation,ordinary_stop_header
    );
    if (
        length < 1 ||
        (size_t)length >= sizeof(request) ||
        !validation_permitted() ||
        send(socket_fd, request, (size_t)length, 0) != (ssize_t)length
    ) {
        (void)close(socket_fd);
        return 0;
    }
    char response[2048] = {0};
    int response_bytes = read_response(socket_fd, response, sizeof(response));
    (void)close(socket_fd);
    return (
        response_bytes > 0 &&
        strncmp(response, "HTTP/1.0 202 ", 13) == 0 &&
        strstr(response, require_v2 ? "\"status\":\"DRAINING\"" :
               "\"status\":\"STOPPING\"") != NULL
    );
}

static int request_graceful_shutdown(pid_t backend_pid,const char *token,
                                     const char *generation,int require_v2) {
    if(!validation_permitted() || !backend_supports_maintenance() || kill(backend_pid,0)!=0)return 0;
    long long before_claim=validation_now_ns();if(!before_claim)return 0;
    stop_deadline_ns=before_claim+15000000000LL;
    handoff_deadline_ns=before_claim+45000000000LL;
    struct timespec window={.tv_sec=(time_t)(stop_deadline_ns/1000000000LL),
                           .tv_nsec=(long)(stop_deadline_ns%1000000000LL)};
    const struct timespec *saved=recovery_io_deadline;recovery_io_deadline=&window;
    int accepted=request_graceful_shutdown_effect(backend_pid,token,generation,require_v2);
    recovery_io_deadline=saved;
    if(!accepted || validation_now_ns()>=stop_deadline_ns) {
        validation_failed=1;validation_cleanup_unresolved=1;
        validation_outcome("PREDECESSOR_DRAIN_STOP",stop_deadline_ns,0,
                           "CLAIM_OR_STOP_NOT_ESTABLISHED",1);
        return 0;
    }
    return 1;
}

static int wait_for_backend_stop(pid_t backend_pid) {
    if(!stop_deadline_ns)stop_deadline_ns=validation_now_ns()+15000000000LL;
    for (int attempt = 0; attempt < 150; ++attempt) {
        if(validation_now_ns()>=stop_deadline_ns) {
            validation_failed=1;validation_cleanup_unresolved=1;
            validation_outcome("PREDECESSOR_DRAIN_STOP",stop_deadline_ns,0,"STOP_WINDOW_EXPIRED",1);
            return 0;
        }
        int process_gone = (kill(backend_pid, 0) != 0 && errno == ESRCH);
        int socket_fd = connect_backend();
        if (socket_fd >= 0) (void)close(socket_fd);
        if (process_gone && socket_fd < 0 && validation_now_ns()<stop_deadline_ns) {
            validation_phase="POST_RETIREMENT";
            validation_deadline_ns=handoff_deadline_ns;
            stop_deadline_ns=0; /* Retirement proved: stop ceiling is fulfilled. */
            return 1;
        }
        usleep(100000);
    }
    return 0;
}

static int no_live_handoff(const char *control_path) {
    struct stat metadata;
    char directory_path[PATH_MAX];
    int length = snprintf(directory_path, sizeof(directory_path), "%s", control_path);
    if (length < 1 || (size_t)length >= sizeof(directory_path)) return 0;
    char *separator = strrchr(directory_path, '/');
    if (separator == NULL) return 0;
    (void)strcpy(separator + 1, "maintenance");
    if (lstat(directory_path, &metadata) != 0) return errno == ENOENT;
    if (!S_ISDIR(metadata.st_mode) || metadata.st_uid != getuid() ||
        (metadata.st_mode & 077) != 0) return 0;
    DIR *directory = opendir(directory_path);
    if (directory == NULL) return 0;
    time_t now = time(NULL);
    int safe = now != (time_t)-1;
    struct dirent *entry;
    while (safe && (entry = readdir(directory)) != NULL) {
        if (strlen(entry->d_name) != 69 ||
            strcmp(entry->d_name + 64, ".json") != 0) continue;
        char generation[65];
        (void)memcpy(generation, entry->d_name, 64);
        generation[64] = '\0';
        if (!valid_token(generation)) continue;
        char source[PATH_MAX];
        char consumed[PATH_MAX];
        if (snprintf(source, sizeof(source), "%s/%s", directory_path, entry->d_name) < 1 ||
            snprintf(consumed, sizeof(consumed), "%s/%s.consumed.json", directory_path,
                     generation) < 1 || lstat(source, &metadata) != 0 ||
            !S_ISREG(metadata.st_mode)) { safe = 0; break; }
        if (metadata.st_mtime > now || now - metadata.st_mtime <= HANDOFF_SECONDS) {
            if (lstat(consumed, &metadata) != 0 || !S_ISREG(metadata.st_mode)) {
                safe = 0;
                break;
            }
        }
    }
    (void)closedir(directory);
    return safe;
}
static int cold_start_has_no_control_or_live_handoff(const char *control_path) {
    struct stat metadata;
    return lstat(control_path,&metadata)!=0 && errno==ENOENT && no_live_handoff(control_path);
}

static int verify_v2_handoff(
    const char *repository, const char *python, const char *python_path,
    const char *control_path, const char *generation, pid_t parent_pid,
    const char *parent_revision, const char *proof
) {
    char maintenance_path[PATH_MAX];
    char parent[32];
    char expected_path[PATH_MAX*2];
    if(snprintf(expected_path,sizeof(expected_path),"%s/src:%s",repository,repository)>=(int)sizeof(expected_path) ||
       strcmp(expected_path,python_path))return 0;
    int length = snprintf(maintenance_path, sizeof(maintenance_path),
                          "%s", control_path);
    if (length < 1 || (size_t)length >= sizeof(maintenance_path)) return 0;
    /* control_path names a file; use its parent, not a child of the file. */
    char *separator = strrchr(maintenance_path, '/');
    if (separator == NULL) return 0;
    (void)strcpy(separator + 1, "maintenance");
    if (snprintf(parent, sizeof(parent), "%ld", (long)parent_pid) < 1) return 0;
    long long now=validation_now_ns(),deadline=now+10000000000LL;
    if(stop_deadline_ns && stop_deadline_ns<deadline)deadline=stop_deadline_ns;
    if(handoff_deadline_ns && handoff_deadline_ns<deadline)deadline=handoff_deadline_ns;
    long long enclosing=validation_deadline_ns;
    if(enclosing && enclosing<deadline)deadline=enclosing;
    validation_deadline_ns=deadline;
    char output[4096]={0};char *arguments[]={(char*)python,"-B","-m","kronos.common.maintenance",
        "verify-v2",maintenance_path,(char*)generation,parent,(char*)parent_revision,NULL};
    int valid=bounded_validation_cli(repository,python,arguments,proof,output,sizeof(output),0,
                                     "POST_RETIREMENT_HANDOFF",10);
    validation_deadline_ns=enclosing;
    return valid;
}

static int qualify_source(const char *repository,const char *python) {
    char gate[PATH_MAX],output[8192]={0};
    if(snprintf(gate,sizeof(gate),"%s/tools/runtime_source_gate.py",repository)>=(int)sizeof(gate))return 0;
    char *arguments[]={(char*)python,"-B",gate,NULL};
    return bounded_validation_cli(repository,python,arguments,NULL,output,sizeof(output),0,"SOURCE_GATE",60);
}

typedef enum BackendStartResult {
    BACKEND_START_READY,
    BACKEND_START_CHILD_EXITED,
    BACKEND_START_READY_TIMEOUT,
    BACKEND_START_INTERNAL_FAILURE,
} BackendStartResult;

typedef struct BackendStartMonitor {
    int (*monotonic_now)(struct timespec *value);
    pid_t (*observe_child)(pid_t child, int *status);
    int (*ready)(void);
    int (*pause)(const struct timespec *duration, struct timespec *remaining);
} BackendStartMonitor;

#define BACKEND_START_READY_TIMEOUT_SECONDS 120
#define BACKEND_START_POLL_NANOSECONDS 100000000L

static int monotonic_now(struct timespec *value) {
    return clock_gettime(CLOCK_MONOTONIC, value);
}

static pid_t observe_backend_child(pid_t child, int *status) {
    return waitpid(child, status, WNOHANG);
}

static int pause_backend_monitor(
    const struct timespec *duration,
    struct timespec *remaining
) {
    return nanosleep(duration, remaining);
}

static const BackendStartMonitor production_backend_start_monitor = {
    .monotonic_now = monotonic_now,
    .observe_child = observe_backend_child,
    .ready = backend_is_ready,
    .pause = pause_backend_monitor,
};

static int time_reached(
    const struct timespec *value,
    const struct timespec *deadline
) {
    return value->tv_sec > deadline->tv_sec ||
        (value->tv_sec == deadline->tv_sec && value->tv_nsec >= deadline->tv_nsec);
}

static struct timespec time_until(
    const struct timespec *value,
    const struct timespec *deadline
) {
    struct timespec remaining = {
        .tv_sec = deadline->tv_sec - value->tv_sec,
        .tv_nsec = deadline->tv_nsec - value->tv_nsec,
    };
    if (remaining.tv_nsec < 0) {
        --remaining.tv_sec;
        remaining.tv_nsec += 1000000000L;
    }
    if (remaining.tv_sec > 0 || remaining.tv_nsec > BACKEND_START_POLL_NANOSECONDS) {
        remaining.tv_sec = 0;
        remaining.tv_nsec = BACKEND_START_POLL_NANOSECONDS;
    }
    return remaining;
}

static BackendStartResult monitor_backend_start(
    pid_t child,
    int timeout_seconds,
    const BackendStartMonitor *monitor
) {
    if (
        monitor == NULL ||
        monitor->monotonic_now == NULL ||
        monitor->observe_child == NULL ||
        monitor->ready == NULL ||
        monitor->pause == NULL ||
        timeout_seconds < 1
    ) {
        return BACKEND_START_INTERNAL_FAILURE;
    }

    struct timespec started;
    if (monitor->monotonic_now(&started) != 0) {
        return BACKEND_START_INTERNAL_FAILURE;
    }
    struct timespec deadline = started;
    deadline.tv_sec += timeout_seconds;
    if(monitor->monotonic_now==monotonic_now && backend_ready_deadline_ns) {
        deadline.tv_sec=(time_t)(backend_ready_deadline_ns/1000000000LL);
        deadline.tv_nsec=(long)(backend_ready_deadline_ns%1000000000LL);
    }

    for (;;) {
        int status = 0;
        errno = 0;
        pid_t observed = monitor->observe_child(child, &status);
        if (observed == child) {
            if(child==admission_child) {
                admission_child_observed=1;admission_child_status=status;
            }
            return BACKEND_START_CHILD_EXITED;
        }
        if (observed != 0 && !(observed < 0 && errno == EINTR)) {
            return BACKEND_START_INTERNAL_FAILURE;
        }

        struct timespec current;
        if (monitor->monotonic_now(&current) != 0) {
            return BACKEND_START_INTERNAL_FAILURE;
        }
        if (time_reached(&current, &deadline)) {
            return BACKEND_START_READY_TIMEOUT;
        }
        if (monitor->ready()) {
            struct timespec completed;
            if(monitor->monotonic_now(&completed)!=0)return BACKEND_START_INTERNAL_FAILURE;
            return time_reached(&completed,&deadline)?BACKEND_START_READY_TIMEOUT:BACKEND_START_READY;
        }

        struct timespec duration = time_until(&current, &deadline);
        struct timespec remaining;
        if (monitor->pause(&duration, &remaining) != 0 && errno != EINTR) {
            return BACKEND_START_INTERNAL_FAILURE;
        }
    }
}

/* ADR-0061: launcher-owned recovery permission. This is not Python authority. */
#define RECOVERY_CLASS "FAILED_ACTIVE_RECOVERY_REPLACEMENT"
#define RECOVERY_SCHEMA "KRONOS-FAILED-ACTIVE-RECOVERY-AUTHORIZATION/1.0.0"
#define RECOVERY_CAPABILITY "WO06H-CAPABILITY-9104752f2f4028b169cd5bcc249477024eb67b1ab2351a30415e40e5fa7e6e40"
/* The immutable owner-reviewed artifact and its canonical EpochStore bytes are
 * separate identities. Exact semantic-equivalence provenance is retained with
 * the release evidence; only RECOVERY_RELATION is production byte authority. */
#define RECOVERY_REVIEW_ARTIFACT_SHA256 "e5d63954815ffa526390e1d5d0e668a8c490371ead305c85a14b43d6c300c58e"
#define RECOVERY_RELATION "707ca654076df91af1935d082a569d8d8c0335f52a08d63a8047ea1a94e4e48b"
#define RECOVERY_DIAGNOSIS "3af1be040e466580111b4e5664d5177aa016aea58988a41cf8189d117931c25c"
#define RECOVERY_PREDECESSOR "cbe496e31d466eb28b7b710ffe9231b4324b1137"
#define RECOVERY_WINDOW_START "2026-09-12T07:50:33.006722+05:30"
#define RECOVERY_WINDOW_END "2026-10-12T07:50:33.006722+05:30"
#define RECOVERY_START_US 1789179633006722LL
#define RECOVERY_END_US 1791771633006722LL
#define RECOVERY_HISTORY_SCHEMA "KRONOS-FAILED-ACTIVE-RECOVERY-AUTHORIZATION/2.0.0"
#define RECOVERY_HISTORY_PREDECESSOR "37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3"
#define RECOVERY_HISTORY_CAPABILITY "WO06H-CAPABILITY-f61cfe6c7395d0ee8554d82946a5a7fa88444c09151f53bc171253a3d35aa31b"
#define RECOVERY_HISTORY_RELATION "c718842b6927ee058b4fd135df6eaa57873ffc0b901c597372110bb46338b0f8"
#define RECOVERY_HISTORY_DIAGNOSIS "c6bb42f497b6e1a2acb056ccc9fd09b2476b73a2e182526fb2bc240e72298d08"
#define RECOVERY_HISTORY_MAX_VALIDITY_US 1800000000LL
/* Closed IWO-07R3 predecessor pins; not generic FAILED_ACTIVE authority. */
#define RECOVERY_SWING_SCHEMA "KRONOS-IWO07R3-RECOVERY-AUTHORIZATION/1.0.0"
#define RECOVERY_SWING_PREDECESSOR "7b0729402687b2f05607ce99a5c99a9cea35568b"
#define RECOVERY_SWING_PID 45583
#define RECOVERY_SWING_START_US 1791996740356956LL
#define RECOVERY_SWING_GENERATION "02a8392f4d88082bf96d3e807c6f1acf00e381ac63f62f7433aecfd2e1c762b3"
#define RECOVERY_SWING_PACKAGE "35a468ca66dfe127479112d777323a63c1221cd381c63d93db09a8b36d4cbd18"
#define RECOVERY_SWING_DIAGNOSIS "014e7571a779a6411655240b92dfbe77bda4f85661c95c243738118b1e3d4d6b"
#define RECOVERY_JSON_TOKENS 8192

typedef struct RecoveryJsonToken { int start, end, next, count; char kind; } RecoveryJsonToken;
typedef struct RecoveryJson {
    const char *text; int length, used; RecoveryJsonToken token[RECOVERY_JSON_TOKENS];
} RecoveryJson;

/* Closed, bounded JSON parser. Duplicate/escaped object keys and invalid JSON
 * are rejected; a marker hidden in a string or another object is never authority. */
static void recovery_json_space(const char *s, int *p) {
    while (s[*p] == ' ' || s[*p] == '\n' || s[*p] == '\r' || s[*p] == '\t') ++*p;
}
static int recovery_json_equal(const RecoveryJson *j, int t, const char *s) {
    return t >= 0 && j->token[t].end-j->token[t].start == (int)strlen(s) &&
        memcmp(j->text+j->token[t].start,s,strlen(s)) == 0;
}
static int recovery_json_parse(RecoveryJson *j, int *p, int depth) {
    recovery_json_space(j->text,p);
    if (*p >= j->length || depth > 32 || j->used >= RECOVERY_JSON_TOKENS) return -1;
    int t=j->used++; RecoveryJsonToken *r=&j->token[t]; memset(r,0,sizeof(*r));
    r->start=*p; char c=j->text[*p];
    if (c=='{' || c=='[') {
        r->kind=c; ++*p; recovery_json_space(j->text,p);
        char close=c=='{'?'}':']';
        if (j->text[*p]!=close) for (;;) {
            if (c=='{') {
                int key=recovery_json_parse(j,p,depth+1);
                if (key<0 || j->token[key].kind!='s' ||
                    memchr(j->text+j->token[key].start,'\\',j->token[key].end-j->token[key].start)) return -1;
                for (int k=t+1;k<key;k=j->token[j->token[k].next].next)
                    if (j->token[k].end-j->token[k].start == j->token[key].end-j->token[key].start &&
                        memcmp(j->text+j->token[k].start,j->text+j->token[key].start,
                               j->token[k].end-j->token[k].start)==0) return -1;
                recovery_json_space(j->text,p); if (j->text[(*p)++]!=':') return -1;
            }
            if (recovery_json_parse(j,p,depth+1)<0) return -1;
            ++r->count; recovery_json_space(j->text,p);
            if (j->text[*p]==close) break;
            if (j->text[(*p)++]!=',') return -1;
        }
        ++*p;
    } else if (c=='"') {
        r->kind='s'; r->start=++*p;
        while (*p<j->length && j->text[*p]!='"') {
            unsigned char v=(unsigned char)j->text[(*p)++]; if (v<32) return -1;
            if (v=='\\') {
                if (*p>=j->length) return -1;
                char esc=j->text[(*p)++];
                if (esc=='u') { for (int n=0;n<4;n++) {
                    if (*p>=j->length) return -1;
                    char h=j->text[(*p)++]; if (!strchr("0123456789abcdefABCDEF",h) || !h) return -1;
                }} else if (!esc || !strchr("\"\\/bfnrt",esc)) return -1;
            }
        }
        if (*p>=j->length) return -1;
        r->end=(*p)++;
    } else {
        r->kind='v'; int start=*p;
        while (*p<j->length && !strchr(" ,\t\r\n}]",j->text[*p])) ++*p;
        int size=*p-start;
        if (!((size==4 && (!memcmp(j->text+start,"true",4) || !memcmp(j->text+start,"null",4))) ||
              (size==5 && !memcmp(j->text+start,"false",5)))) {
            int q=start; if(j->text[q]=='-') ++q;
            if(j->text[q]=='0') ++q; else {
                if(j->text[q]<'1'||j->text[q]>'9') return -1;
                while(j->text[q]>='0'&&j->text[q]<='9') ++q;
            }
            if(j->text[q]=='.') { ++q; int a=q; while(j->text[q]>='0'&&j->text[q]<='9')++q; if(a==q)return -1; }
            if(j->text[q]=='e'||j->text[q]=='E') { ++q;if(j->text[q]=='+'||j->text[q]=='-')++q;
                int a=q;while(j->text[q]>='0'&&j->text[q]<='9')++q;if(a==q)return -1; }
            if(q!=*p) return -1;
        }
    }
    if (r->kind!='s') r->end=*p;
    r->next=j->used; return t;
}
static int recovery_json_document(RecoveryJson *j,const char *text) {
    memset(j,0,sizeof(*j));j->text=text;j->length=(int)strlen(text);int p=0;
    if(recovery_json_parse(j,&p,0)!=0 || j->token[0].kind!='{') return 0;
    recovery_json_space(text,&p);return p==j->length;
}
static int recovery_json_get(const RecoveryJson *j,int object,const char *key) {
    if(object<0 || j->token[object].kind!='{')return -1;
    for(int k=object+1;k<j->token[object].next;k=j->token[j->token[k].next].next)
        if(recovery_json_equal(j,k,key))return j->token[k].next;
    return -1;
}
static int recovery_field(const RecoveryJson *j,int obj,const char *key,const char *value) {
    int t=recovery_json_get(j,obj,key);
    char kind=(!strcmp(value,"true") || !strcmp(value,"false") || !strcmp(value,"null"))?'v':'s';
    return t>=0 && j->token[t].kind==kind && recovery_json_equal(j,t,value);
}
static int recovery_string(const RecoveryJson *j,int obj,const char *key,char *out,size_t cap) {
    int t=recovery_json_get(j,obj,key);if(t<0 || j->token[t].kind!='s')return 0;
    int n=j->token[t].end-j->token[t].start;
    if(n<1 || (size_t)n>=cap || memchr(j->text+j->token[t].start,'\\',(size_t)n))return 0;
    memcpy(out,j->text+j->token[t].start,(size_t)n);out[n]=0;return 1;
}
static long long recovery_integer(const RecoveryJson *j,int obj,const char *key) {
    int t=recovery_json_get(j,obj,key);char buf[32];if(t<0 || j->token[t].kind!='v')return -1;
    int n=j->token[t].end-j->token[t].start;if(n<1 || n>=31)return -1;
    memcpy(buf,j->text+j->token[t].start,(size_t)n);buf[n]=0;char *end=NULL;errno=0;
    long long v=strtoll(buf,&end,10);return errno || *end || v<0 ? -1:v;
}
static long long recovery_now_us(void) {
    struct timeval t;if(gettimeofday(&t,NULL)!=0)return -1;
    return (long long)t.tv_sec*1000000+t.tv_usec;
}
static int recovery_safe_path(const char *path,int directory,int private_mode) {
    char real[PATH_MAX],ancestor[PATH_MAX];struct stat s;
    if(!path || path[0]!='/' || strlen(path)>=PATH_MAX || !realpath(path,real) || strcmp(path,real))return 0;
    strcpy(ancestor,path);
    for (;;) {
        if(lstat(ancestor,&s)!=0 || S_ISLNK(s.st_mode))return 0;
        char *slash=strrchr(ancestor,'/');if(slash==ancestor)break;*slash=0;
    }
    if(lstat(path,&s)!=0 || s.st_uid!=getuid() || (directory?!S_ISDIR(s.st_mode):!S_ISREG(s.st_mode)))return 0;
    return !private_mode || (s.st_mode&077)==0;
}
static int recovery_separate_bundle(const char *rollback, const char *installed) {
    struct stat a,b;
    return recovery_safe_path(rollback,1,0) && recovery_safe_path(installed,1,0) &&
        strcmp(rollback,installed) && stat(rollback,&a)==0 && stat(installed,&b)==0 &&
        (a.st_dev!=b.st_dev || a.st_ino!=b.st_ino);
}
static int recovery_read_file(const char *path,char *out,size_t capacity,int private_mode) {
    if(!recovery_safe_path(path,0,private_mode))return 0;
    int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return 0;struct stat s;
    int ok=fstat(fd,&s)==0 && S_ISREG(s.st_mode) && s.st_uid==getuid() &&
        (!private_mode || !(s.st_mode&077)) && s.st_size>0 && (size_t)s.st_size<capacity;
    size_t used=0;
    while(ok && used<(size_t)s.st_size) {ssize_t n=read(fd,out+used,(size_t)s.st_size-used);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=0;break;}used+=(size_t)n;}
    char extra; if(ok && read(fd,&extra,1)!=0)ok=0;close(fd);
    if(!ok || memchr(out,0,used))return 0;out[used]=0;return 1;
}
static int recovery_file_digest(const char *path,char out[65],int private_mode) {
    if(!recovery_safe_path(path,0,private_mode))return 0;
    int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return 0;struct stat s;
    if(fstat(fd,&s)!=0 || !S_ISREG(s.st_mode) || s.st_uid!=getuid() ||
       (private_mode && (s.st_mode&077))){close(fd);return 0;}
    CC_SHA256_CTX context;CC_SHA256_Init(&context);unsigned char buffer[16384],digest[32];ssize_t n;
    while((n=read(fd,buffer,sizeof(buffer)))!=0){if(n<0){if(errno==EINTR)continue;close(fd);return 0;}
        CC_SHA256_Update(&context,buffer,(CC_LONG)n);}
    close(fd);CC_SHA256_Final(digest,&context);
    for(int i=0;i<32;i++)snprintf(out+2*i,3,"%02x",digest[i]);return 1;
}
/* P01: native-only journal publication. The root/head must already have been
 * established by a separately authorized installation activation. No path here
 * creates that root, reconstructs history, deletes an intent or repairs a head.
 * An immutable head-N.json is the publication intent AND historical head bytes;
 * finding N+1 while the selected head is N denies the next invocation. */
#define NATIVE_HEAD_SCHEMA "KRONOS_RESTORATION_ADMISSION_HEAD_V1"
#define NATIVE_PHASE_SCHEMA "KRONOS_NATIVE_ADMISSION_PHASE_V1"
#define NATIVE_DOCUMENT_BYTES 65537
typedef struct {
    int root;
    pid_t writer;
    long long sequence;
    char installation[65],state[64],incident[201],identity[201],record_digest[65];
    char head_digest[65],head[NATIVE_DOCUMENT_BYTES];
} NativeAdmissionJournal;
static NativeAdmissionJournal native_journal={.root=-1};
/* No initializer can populate this policy. A separately reviewed source and
 * artifact release must embed the identical canonical disposition in Python. */
static const char *approved_initialization_disposition = NULL;
static const char *initialization_policy(void) { return approved_initialization_disposition; }
static char initialization_disposition_digest[65];
static int native_copy_json(const RecoveryJson *,int,char *,size_t);
static int native_json_text(const char *);

static int native_identity(const char *value) {
    if(!value || !*value || strlen(value)>200)return 0;
    for(const unsigned char *p=(const unsigned char*)value;*p;p++)
        if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||strchr("._:-",*p)))return 0;
    return 1;
}
static void native_digest(const void *raw,size_t size,char result[65]) {
    unsigned char bytes[CC_SHA256_DIGEST_LENGTH];CC_SHA256(raw,(CC_LONG)size,bytes);
    for(size_t i=0;i<sizeof(bytes);i++)snprintf(result+i*2,3,"%02x",bytes[i]);
}
static int persistent_anchor_matches(int fd,const char *path,dev_t device,ino_t inode,uid_t owner) {
    if(device!=approved_admission_device)return 0;
    struct stat metadata;if(fstat(fd,&metadata)!=0 || (metadata.st_mode&0777)!=0700)return 0;
    RecoveryJson policy;char volume[37],expected[64];uint64_t file_id;
    return approved_persistent_binding && recovery_json_document(&policy,approved_persistent_binding) &&
        policy.token[0].count==11 &&
        recovery_field(&policy,0,"schema","KRONOS_PERSISTENT_ANCHOR_BINDING_V1") &&
        recovery_field(&policy,0,"anchor_path",path) && recovery_field(&policy,0,"required_mode","0700") &&
        recovery_integer(&policy,0,"owner")==owner && recovery_integer(&policy,0,"file_id")== (long long)inode &&
        recovery_field(&policy,0,"bundle_path",canonical_bundle) &&
        recovery_field(&policy,0,"bundle_id","com.project-kronos.browser-v1") &&
        recovery_string(&policy,0,"volume_uuid",expected,sizeof(expected)) &&
        descriptor_filesystem_identity(fd,volume,&file_id) && file_id==(uint64_t)inode && !strcmp(volume,expected);
}
static int native_same_file(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_mode==b->st_mode &&
        a->st_uid==b->st_uid && a->st_size==b->st_size &&
        a->st_mtimespec.tv_sec==b->st_mtimespec.tv_sec && a->st_mtimespec.tv_nsec==b->st_mtimespec.tv_nsec &&
        a->st_ctimespec.tv_sec==b->st_ctimespec.tv_sec && a->st_ctimespec.tv_nsec==b->st_ctimespec.tv_nsec;
}
static int native_read(int root,const char *name,char *out,size_t capacity) {
    if(root<0 || !native_identity(name) || !out || capacity<2)return 0;
    int fd=openat(root,name,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(fd<0)return 0;
    struct stat before,after,named;size_t used=0;
    int ok=fstat(fd,&before)==0 && S_ISREG(before.st_mode) && before.st_uid==getuid() &&
        (before.st_mode&0777)==0600 && before.st_size>0 && (size_t)before.st_size<capacity;
    while(ok && used<(size_t)before.st_size) {
        ssize_t n=read(fd,out+used,(size_t)before.st_size-used);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=0;break;}used+=(size_t)n;
    }
    char extra;
    ok=ok && read(fd,&extra,1)==0 && fstat(fd,&after)==0 &&
        fstatat(root,name,&named,AT_SYMLINK_NOFOLLOW)==0 &&
        native_same_file(&before,&after) && native_same_file(&after,&named) && !memchr(out,0,used);
    close(fd);if(!ok)return 0;out[used]=0;return 1;
}
static int native_root_bound(void) {
    struct stat held,named;
    return native_journal.root>=0 && native_journal.writer==getpid() && admission_still_bound() &&
        fstat(native_journal.root,&held)==0 &&
        fstatat(admission_descriptor,"failed-successor-restore-v1",&named,AT_SYMLINK_NOFOLLOW)==0 &&
        S_ISDIR(held.st_mode) && held.st_uid==getuid() && (held.st_mode&0777)==0700 &&
        held.st_dev==named.st_dev && held.st_ino==named.st_ino && S_ISDIR(named.st_mode);
}
static int native_exclusive(const char *name,const char *raw) {
    if(!native_identity(name) || !raw || !*raw || strlen(raw)>=NATIVE_DOCUMENT_BYTES ||
       !native_root_bound() || !validation_permitted())return 0;
    int fd=openat(native_journal.root,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return 0;
    size_t size=strlen(raw),used=0;int ok=1;
    while(used<size) {
        ssize_t n=write(fd,raw+used,size-used);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=0;break;}used+=(size_t)n;
    }
    if(ok && fsync(fd)!=0)ok=0;
    if(close(fd)!=0)ok=0;
    if(ok && fsync(native_journal.root)!=0)ok=0;
    char observed[NATIVE_DOCUMENT_BYTES];
    return ok && native_read(native_journal.root,name,observed,sizeof(observed)) &&
        !strcmp(observed,raw) && native_root_bound() && validation_permitted();
    /* Partial/uncertain bytes remain permanently present; never unlink/retry. */
}
static int native_head_record_matches(const RecoveryJson *head,const char *raw) {
    RecoveryJson record;
    if(!recovery_json_document(&record,raw))return 0;
    if(recovery_field(head,0,"state","RESTORATION_RESERVED"))
        return recovery_field(&record,0,"schema","KRONOS_FAILED_SUCCESSOR_RESTORATION_RESERVATION_V1") &&
            recovery_field(&record,0,"reservation_id",native_journal.identity) &&
            recovery_field(&record,0,"incident_id",native_journal.incident) &&
            recovery_field(&record,0,"installation_identity",native_journal.installation) &&
            recovery_field(&record,0,"state","RESTORATION_RESERVED");
    return recovery_field(&record,0,"schema",NATIVE_PHASE_SCHEMA) &&
        recovery_field(&record,0,"identity",native_journal.identity) &&
        recovery_field(&record,0,"installation_identity",native_journal.installation) &&
        recovery_field(&record,0,"phase",native_journal.state);
}
static int initialization_equal(const RecoveryJson *a,int x,const RecoveryJson *b,int y) {
    if(x<0 || y<0)return 0;
    int n=a->token[x].end-a->token[x].start,m=b->token[y].end-b->token[y].start;
    return n==m && !memcmp(a->text+a->token[x].start,b->text+b->token[y].start,(size_t)n);
}
static int initialization_read(int directory,const char *name,char *raw) {
    if(!validation_permitted() || !admission_still_bound())return 0;
    int fd=openat(directory,name,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
    if(fd<0)return 0;
    struct stat before,after,named;
    int ok=fstat(fd,&before)==0 && S_ISREG(before.st_mode) && before.st_uid==getuid() &&
        (before.st_mode&0777)==0600 && fsync(fd)==0 &&
        native_read(directory,name,raw,NATIVE_DOCUMENT_BYTES) &&
        fstat(fd,&after)==0 && fstatat(directory,name,&named,AT_SYMLINK_NOFOLLOW)==0 &&
        native_same_file(&before,&after) && native_same_file(&after,&named);
    if(close(fd)!=0)ok=0;
    return ok && fsync(directory)==0 && native_root_bound() && validation_permitted();
}
static int initialization_reference(const RecoveryJson *j,int ref,const char *expected,char *raw) {
    char path[PATH_MAX],directory[PATH_MAX],digest[65],actual[65],identity[201];
    if(ref<0 || j->token[ref].kind!='{' || j->token[ref].count!=4 ||
       !recovery_string(j,ref,"path",path,sizeof(path)) ||
       !recovery_string(j,ref,"sha256",digest,sizeof(digest)) || !valid_token(digest) ||
       !recovery_string(j,ref,"identity",identity,sizeof(identity)) || !native_identity(identity) ||
       !recovery_safe_path(path,0,1) || (expected && strcmp(path,expected)))return 0;
    strcpy(directory,path);char *name=strrchr(directory,'/');if(!name || name==directory)return 0;
    *name++=0;int fd=open(directory,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return 0;
    struct stat dir;if(fstat(fd,&dir)!=0 || dir.st_uid!=getuid() || (dir.st_mode&0777)!=0700){close(fd);return 0;}
    int ok=initialization_read(fd,name,raw);if(close(fd)!=0)ok=0;
    if(!ok || recovery_integer(j,ref,"bytes")!=(long long)strlen(raw))return 0;
    native_digest(raw,strlen(raw),actual);return !strcmp(actual,digest);
}
static long long initialization_utc(const char *value) {
    struct tm t={0};char prefix[32];const char *end=strptime(value,"%Y-%m-%dT%H:%M:%S",&t);
    if(!end)return -1;long long micro=0;int digits=0;
    if(*end=='.'){end++;while(*end>='0'&&*end<='9'&&digits<6){micro=micro*10+(*end++-'0');digits++;}
        if(!digits)return -1;while(digits++<6)micro*=10;}
    if(strcmp(end,"+00:00") && strcmp(end,"Z"))return -1;
    time_t seconds=timegm(&t);if(seconds<0 || !strftime(prefix,sizeof(prefix),"%Y-%m-%dT%H:%M:%S",&t) ||
        strncmp(prefix,value,19))return -1;
    return (long long)seconds*1000000+micro;
}
static int initialization_source_reference(const RecoveryJson *j,int ref) {
    char path[PATH_MAX],parent[PATH_MAX],digest[65],identity[201],actual[65];
    long long expected=ref<0?-1:recovery_integer(j,ref,"bytes");
    if(ref<0 || j->token[ref].kind!='{' || j->token[ref].count!=4 || expected<1 || expected>8*1024*1024 ||
       !recovery_string(j,ref,"path",path,sizeof(path)) || !recovery_safe_path(path,0,1) ||
       !recovery_string(j,ref,"identity",identity,sizeof(identity)) || !native_identity(identity) ||
       !recovery_string(j,ref,"sha256",digest,sizeof(digest)) || !valid_token(digest))return 0;
    strcpy(parent,path);char *name=strrchr(parent,'/');if(!name || name==parent)return 0;*name++=0;
    int dir=open(parent,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(dir<0)return 0;
    struct stat folder,before,after,named;int fd=openat(dir,name,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
    int ok=fd>=0 && fstat(dir,&folder)==0 && folder.st_uid==getuid() && (folder.st_mode&0777)==0700 &&
        fstat(fd,&before)==0 && S_ISREG(before.st_mode) && before.st_uid==getuid() &&
        (before.st_mode&0777)==0600 && before.st_size==expected;
    CC_SHA256_CTX context;CC_SHA256_Init(&context);unsigned char buffer[65536],hash[32];long long used=0;
    while(ok) {
        if(!validation_permitted() || !native_root_bound()){ok=0;break;}
        ssize_t n=read(fd,buffer,sizeof(buffer));if(n<0 && errno==EINTR)continue;
        if(n<0){ok=0;break;}if(n==0)break;used+=n;if(used>expected){ok=0;break;}
        CC_SHA256_Update(&context,buffer,(CC_LONG)n);
    }
    if(ok)ok=used==expected && fsync(fd)==0 && fstat(fd,&after)==0 &&
        fstatat(dir,name,&named,AT_SYMLINK_NOFOLLOW)==0 && native_same_file(&before,&after) && native_same_file(&after,&named);
    if(fd>=0 && close(fd)!=0)ok=0;
    if(ok && fsync(dir)!=0)ok=0;if(close(dir)!=0)ok=0;
    CC_SHA256_Final(hash,&context);for(size_t i=0;i<sizeof(hash);i++)snprintf(actual+2*i,3,"%02x",hash[i]);
    return ok && !strcmp(actual,digest) && native_root_bound() && validation_permitted();
}
static int initialization_process(const RecoveryJson *j,int obj) {
    char birth[65],runtime[65],revision[65];
    return obj>=0 && j->token[obj].kind=='{' && j->token[obj].count==4 &&
        recovery_integer(j,obj,"pid")>=2 && recovery_string(j,obj,"kernel_birth",birth,sizeof(birth)) && valid_token(birth) &&
        recovery_string(j,obj,"runtime_identity",runtime,sizeof(runtime)) && valid_token(runtime) &&
        recovery_string(j,obj,"revision",revision,sizeof(revision)) &&
        (valid_revision(revision) || (strlen(revision)==64 && valid_token(revision)));
}
static int initialization_target(const RecoveryJson *j,int obj) {
    char value[PATH_MAX];
    if(obj<0 || j->token[obj].kind!='{' || j->token[obj].count!=7 ||
       !recovery_string(j,obj,"revision",value,sizeof(value)) ||
       (!valid_revision(value) && !(strlen(value)==64 && valid_token(value))))return 0;
    const char *hashes[]={"tree_sha256","source_manifest_sha256","artifact_manifest_sha256","pinned_capture_sha256"};
    for(size_t k=0;k<4;k++)if(!recovery_string(j,obj,hashes[k],value,sizeof(value)) || !valid_token(value))return 0;
    return recovery_string(j,obj,"origin_url",value,sizeof(value)) &&
        recovery_string(j,obj,"source_ref",value,sizeof(value));
}
static pid_t setup_activation_writer=0;
static long long setup_activation_deadline=0;
static char setup_activation_intent_sha256[65]={0};
static char setup_activation_parent_birth[65]={0};
static int setup_activation_lineage(const RecoveryJson *intent,const char *raw) {
    RecoveryJson package,activation,policy,phase,head;
    char body[NATIVE_DOCUMENT_BYTES],active[NATIVE_DOCUMENT_BYTES],installed[NATIVE_DOCUMENT_BYTES],
        record[NATIVE_DOCUMENT_BYTES],hraw[NATIVE_DOCUMENT_BYTES],path[PATH_MAX],digest[65],id[201],name[240];
    if(!approved_ordinary_restart_policy ||
       !recovery_json_document(&policy,approved_ordinary_restart_policy) || policy.token[0].count!=7 ||
       !recovery_field(&policy,0,"schema","ORDINARY_SAME_RELEASE_V1") ||
       !recovery_field(&policy,0,"scope","ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP") ||
       !recovery_field(&policy,0,"installation_identity",native_journal.installation) ||
       !initialization_reference(intent,recovery_json_get(intent,0,"input"),NULL,body) ||
       !recovery_json_document(&package,body) || package.token[0].count!=5 ||
       !recovery_field(&package,0,"schema","KRONOS_PREPARED_ORDINARY_ACTIVATION_V1"))return 0;
    snprintf(path,sizeof(path),"%s/ordinary-start-v1/activation.json",admission_anchor);
    if(!initialization_reference(&package,recovery_json_get(&package,0,"activation"),NULL,active) ||
       !recovery_json_document(&activation,active) || activation.token[0].count!=9 ||
       !recovery_field(&activation,0,"schema","KRONOS_ORDINARY_ACTIVATION_V1") ||
       !recovery_field(&activation,0,"installation_identity",native_journal.installation) ||
       !recovery_string(&activation,0,"identity",id,sizeof(id)) || !native_identity(id))return 0;
    native_digest(approved_ordinary_restart_policy,strlen(approved_ordinary_restart_policy),digest);
    if(!recovery_field(&activation,0,"policy_sha256",digest))return 0;
    native_digest(approved_persistent_binding,strlen(approved_persistent_binding),digest);
    if(!recovery_field(&policy,0,"binding_sha256",digest))return 0;
    native_digest(initialization_policy(),strlen(initialization_policy()),digest);
    if(!recovery_field(&activation,0,"genesis_disposition_sha256",digest) ||
       !recovery_field(&policy,0,"genesis_disposition_sha256",digest) ||
       !initialization_equal(&activation,recovery_json_get(&activation,0,"release_id"),&policy,recovery_json_get(&policy,0,"release_id")))return 0;
    int directory=openat(admission_descriptor,"ordinary-start-v1",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(directory<0)return 0;
    struct stat dbefore,dafter,dnamed;
    int ok=fstat(directory,&dbefore)==0 && S_ISDIR(dbefore.st_mode) && dbefore.st_uid==getuid() &&
        (dbefore.st_mode&0777)==0700 && initialization_read(directory,"activation.json",record) && !strcmp(record,active) &&
        initialization_read(directory,"installed-selection.json",installed) && fsync(directory)==0 &&
        fstat(directory,&dafter)==0 && fstatat(admission_descriptor,"ordinary-start-v1",&dnamed,AT_SYMLINK_NOFOLLOW)==0 &&
        native_same_file(&dbefore,&dafter) && native_same_file(&dafter,&dnamed);
    if(close(directory)!=0)ok=0;if(!ok)return 0;
    snprintf(path,sizeof(path),"%s/ordinary-start-v1/installed-selection.json",admission_anchor);
    int selected=recovery_json_get(&activation,0,"selection");
    native_digest(installed,strlen(installed),digest);
    if(!recovery_field(&activation,selected,"path",path) || !recovery_field(&policy,0,"installed_selection_path",path) ||
       !recovery_field(&activation,selected,"sha256",digest) || recovery_integer(&activation,selected,"bytes")!=(long long)strlen(installed) ||
       !initialization_reference(&package,recovery_json_get(&package,0,"selection"),NULL,record) || strcmp(record,installed))return 0;
    if(!native_read(native_journal.root,"admission-head.json",hraw,sizeof(hraw)) || !recovery_json_document(&head,hraw))return 0;
    long long sequence=recovery_integer(&head,0,"sequence");if(sequence<1 || sequence>1000000000)return 0;
    int found=0;char actual_ref[PATH_MAX+400],intent_ref[PATH_MAX+400],intent_digest[65];
    native_digest(active,strlen(active),digest);native_digest(raw,strlen(raw),intent_digest);
    snprintf(actual_ref,sizeof(actual_ref),"{\"bytes\":%zu,\"identity\":\"%s\",\"path\":\"%s/ordinary-start-v1/activation.json\",\"sha256\":\"%s\"}",strlen(active),id,admission_anchor,digest);
    snprintf(intent_ref,sizeof(intent_ref),"{\"bytes\":%zu,\"identity\":\"setup-activation\",\"path\":\"%s/controlled-setup-v1/activation.intent.json\",\"sha256\":\"%s\"}",strlen(raw),admission_anchor,intent_digest);
    RecoveryJson ar,ir;if(!recovery_json_document(&ar,actual_ref) || !recovery_json_document(&ir,intent_ref))return 0;
    for(long long n=1;n<=sequence;n++) {
        snprintf(name,sizeof(name),"head-%lld.json",n);
        if(!native_read(native_journal.root,name,hraw,sizeof(hraw)) || !recovery_json_document(&head,hraw))return 0;
        if(!recovery_field(&head,0,"state","ORDINARY_ACTIVATED"))continue;
        if(!recovery_string(&head,0,"active_reservation_id",id,sizeof(id)))return 0;
        snprintf(name,sizeof(name),"%s.json",id);
        if(!native_read(native_journal.root,name,record,sizeof(record)) || !recovery_json_document(&phase,record))return 0;
        native_digest(record,strlen(record),digest);
        int details=recovery_json_get(&phase,0,"details");
        if(!recovery_field(&head,0,"active_reservation_sha256",digest) || details<0 || phase.token[details].count!=2 ||
           !recovery_field(&phase,0,"schema",NATIVE_PHASE_SCHEMA) || !recovery_field(&phase,0,"phase","ORDINARY_ACTIVATED") ||
           !recovery_field(&phase,0,"installation_identity",native_journal.installation) ||
           !initialization_equal(&phase,recovery_json_get(&phase,0,"selection"),&activation,selected) ||
           !initialization_equal(&phase,recovery_json_get(&phase,details,"activation"),&ar,0) ||
           !initialization_equal(&phase,recovery_json_get(&phase,details,"setup_attempt"),&ir,0) ||
           !initialization_equal(&phase,recovery_json_get(&phase,0,"parent"),intent,recovery_json_get(intent,0,"parent")))return 0;
        found++;
    }
    if(found==1)return validation_permitted() && admission_still_bound();
    /* Only this entered native publication may traverse its own complete
     * physical preparation before the journal commit. It admits no caller,
     * survives no exit and cannot clear a different/expired intent. */
    int timing=recovery_json_get(intent,0,"timing"),parent=recovery_json_get(intent,0,"parent");
    return found==0 && sequence==1 && setup_activation_writer==getpid() &&
        setup_activation_deadline==validation_current_deadline() && !strcmp(setup_activation_intent_sha256,intent_digest) &&
        recovery_integer(intent,parent,"pid")==getpid() && recovery_field(intent,parent,"kernel_birth",setup_activation_parent_birth) &&
        recovery_integer(intent,timing,"deadline_ns")==validation_current_deadline() &&
        recovery_field(intent,timing,"boot_session",operation_boot_identity) && validation_permitted() && admission_still_bound();
}
static int setup_genesis_references(const RecoveryJson *evidence) {
    int fd=openat(admission_descriptor,"controlled-setup-v1",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return errno==ENOENT;
    struct stat before,after,named;
    int ok=fstat(fd,&before)==0 && S_ISDIR(before.st_mode) && before.st_uid==getuid() && (before.st_mode&0777)==0700;
    int scan=ok?dup(fd):-1;DIR *directory=scan>=0?fdopendir(scan):NULL;
    if(!directory){if(scan>=0)close(scan);close(fd);return 0;}
    int enrollment=0,stale=0,original=0;struct dirent *entry;
    while(ok && (entry=readdir(directory))) {
        const char *name=entry->d_name;if(!strcmp(name,".") || !strcmp(name,".."))continue;
        const char *identity=NULL;
        if(!strcmp(name,"enrollment.intent.json")){enrollment++;identity="setup-enrollment";}
        else if(!strcmp(name,"stale-control.intent.json")){stale++;identity="setup-stale-control";}
        else if(!strcmp(name,"stale-control.original")){original++;continue;}
        else if(!strcmp(name,"activation.intent.json"))identity="setup-activation";
        else {ok=0;break;}
        char raw[NATIVE_DOCUMENT_BYTES],path[PATH_MAX],digest[65],observed[NATIVE_DOCUMENT_BYTES];
        if(!initialization_read(fd,name,raw)){ok=0;break;}
        RecoveryJson attempt;
        if(!recovery_json_document(&attempt,raw) || attempt.token[0].count!=11 ||
           !recovery_field(&attempt,0,"schema","KRONOS_CONTROLLED_SETUP_ATTEMPT_V1") ||
           !recovery_field(&attempt,0,"identity",identity) ||
           !recovery_field(&attempt,0,"installation_identity",native_journal.installation) ||
           !recovery_field(&attempt,0,"original_outcome","UNPROVED") || !approved_persistent_binding){ok=0;break;}
        native_digest(approved_persistent_binding,strlen(approved_persistent_binding),digest);
        if(!recovery_field(&attempt,0,"binding_sha256",digest)){ok=0;break;}
        if(!strcmp(identity,"setup-activation")) {
            if(!recovery_field(&attempt,0,"operation","ACTIVATE_SELECTION") ||
               !recovery_field(&attempt,0,"preserved","null") || !setup_activation_lineage(&attempt,raw)){ok=0;break;}
            continue;
        }
        if(!strcmp(identity,"setup-stale-control")) {
            snprintf(path,sizeof(path),"%s/controlled-setup-v1/stale-control.original",admission_anchor);
            if(!recovery_field(&attempt,0,"operation","PRESERVE_STALE_CONTROL") ||
               !initialization_reference(&attempt,recovery_json_get(&attempt,0,"preserved"),path,observed)){ok=0;break;}
        } else if(!recovery_field(&attempt,0,"operation","PLACE_ENROLLMENT") ||
                  !recovery_field(&attempt,0,"preserved","null")){ok=0;break;}
        native_digest(raw,strlen(raw),digest);snprintf(path,sizeof(path),"%s/controlled-setup-v1/%s",admission_anchor,name);
        int count=0;const char *lists[]={"observations","subsequent_observations"};
        for(size_t k=0;k<2;k++) {
            int list=recovery_json_get(evidence,0,lists[k]);
            if(list<0 || evidence->token[list].kind!='['){ok=0;break;}
            for(int i=list+1;i<evidence->token[list].next;i=evidence->token[i].next)
                if(recovery_field(evidence,i,"path",path)) {
                    if(!recovery_field(evidence,i,"identity",identity) || !recovery_field(evidence,i,"sha256",digest) ||
                       recovery_integer(evidence,i,"bytes")!=(long long)strlen(raw) ||
                       !initialization_reference(evidence,i,path,observed) || strcmp(raw,observed)){ok=0;break;}
                    count++;
                }
        }
        if(count!=1)ok=0;
    }
    if(closedir(directory)!=0)ok=0;
    ok=ok && enrollment==1 && stale==original && stale<=1 && fsync(fd)==0 &&
        fstat(fd,&after)==0 && fstatat(admission_descriptor,"controlled-setup-v1",&named,AT_SYMLINK_NOFOLLOW)==0 &&
        before.st_dev==after.st_dev && before.st_ino==after.st_ino && before.st_mtimespec.tv_sec==after.st_mtimespec.tv_sec &&
        before.st_mtimespec.tv_nsec==after.st_mtimespec.tv_nsec && native_same_file(&after,&named);
    if(close(fd)!=0)ok=0;
    return ok && validation_permitted() && admission_still_bound();
}
static int native_initialization_admitted(void) {
    const char *raw=initialization_policy();
    RecoveryJson policy,attempt,first,phase,evidence,item,selected;
    char attempt_raw[NATIVE_DOCUMENT_BYTES],first_raw[NATIVE_DOCUMENT_BYTES],phase_raw[NATIVE_DOCUMENT_BYTES],
        scratch[NATIVE_DOCUMENT_BYTES],current[NATIVE_DOCUMENT_BYTES],retained[NATIVE_DOCUMENT_BYTES],
        path[PATH_MAX],name[240],id[201],digest[65],previous[65],stamp[80];
    if(!raw || strlen(raw)>=NATIVE_DOCUMENT_BYTES || !native_root_bound() || !validation_permitted() ||
       !recovery_json_document(&policy,raw) || policy.token[0].count!=11 ||
       !recovery_field(&policy,0,"schema","KRONOS_ADMISSION_INITIALIZATION_DISPOSITION_V1") ||
       !recovery_field(&policy,0,"scope","ADMIT_THIS_RETAINED_GENESIS_LINEAGE") ||
       !recovery_field(&policy,0,"installation_identity",native_journal.installation) ||
       !recovery_string(&policy,0,"identity",id,sizeof(id)) || !native_identity(id) ||
       !recovery_string(&policy,0,"decided_at",stamp,sizeof(stamp)) || initialization_utc(stamp)<0 ||
       (!recovery_field(&policy,0,"original_outcome","UNPROVED_OR_LATE_UNRESOLVED") &&
        !recovery_field(&policy,0,"original_outcome","OBSERVED_PREPARED_WITHIN_ORIGINAL_DEADLINE")))return 0;
    snprintf(path,sizeof(path),"%s/failed-successor-restore-v1/initialization-attempt.json",admission_anchor);
    if(!initialization_reference(&policy,recovery_json_get(&policy,0,"attempt"),path,attempt_raw) ||
       !recovery_json_document(&attempt,attempt_raw) || attempt.token[0].count!=10 ||
       !recovery_field(&attempt,0,"schema","KRONOS_ADMISSION_INITIALIZATION_ATTEMPT_V1") ||
       !recovery_string(&attempt,0,"attempt_id",id,sizeof(id)) || !native_identity(id) ||
       recovery_integer(&attempt,0,"deadline_ns")<=0 ||
       !recovery_string(&attempt,0,"started_at",stamp,sizeof(stamp)) || initialization_utc(stamp)<0 ||
       !initialization_process(&attempt,recovery_json_get(&attempt,0,"parent")))return 0;
    long long started_at=initialization_utc(stamp);
    int install=recovery_json_get(&attempt,0,"installation");
    struct stat anchor;
    if(install<0 || attempt.token[install].kind!='{' || attempt.token[install].count!=8 ||
       fstat(admission_descriptor,&anchor)!=0 || !recovery_field(&attempt,install,"identity",native_journal.installation) ||
       !recovery_field(&attempt,install,"anchor_path",admission_anchor) ||
       recovery_integer(&attempt,install,"device")!=(long long)(approved_persistent_binding?approved_admission_device:anchor.st_dev) ||
       recovery_integer(&attempt,install,"inode")!=(long long)anchor.st_ino ||
       recovery_integer(&attempt,install,"owner")!=(long long)anchor.st_uid ||
       !recovery_field(&attempt,install,"bundle_path",canonical_bundle) ||
       !initialization_reference(&attempt,recovery_json_get(&attempt,0,"selection"),NULL,scratch) ||
       !recovery_json_document(&selected,scratch) || selected.token[0].count!=12 ||
       !recovery_field(&selected,0,"schema","KRONOS_NATIVE_STARTUP_SELECTION_V1") ||
       !recovery_field(&selected,0,"mode","ORDINARY") || !recovery_field(&selected,0,"permit","null") ||
       !initialization_equal(&selected,recovery_json_get(&selected,0,"installation"),&attempt,install))return 0;
    char repository_path[PATH_MAX],core[3*PATH_MAX+400],core_digest[65];
    if(!recovery_field(&attempt,install,"bundle_id","com.project-kronos.browser-v1") ||
       !recovery_string(&attempt,install,"repository_path",repository_path,sizeof(repository_path)) ||
       repository_path[0]!='/' || !native_json_text(repository_path))return 0;
    int core_size=snprintf(core,sizeof(core),"{\"anchor_path\":\"%s\",\"bundle_id\":\"com.project-kronos.browser-v1\",\"bundle_path\":\"%s\",\"device\":%lld,\"inode\":%lld,\"owner\":%lld,\"repository_path\":\"%s\"}",
        admission_anchor,canonical_bundle,(long long)(approved_persistent_binding?approved_admission_device:anchor.st_dev),(long long)anchor.st_ino,(long long)anchor.st_uid,repository_path);
    if(core_size<1 || (size_t)core_size>=sizeof(core))return 0;
    native_digest(core,(size_t)core_size,core_digest);if(strcmp(core_digest,native_journal.installation))return 0;
    if(approved_persistent_binding) {
        RecoveryJson binding;char enrollment[NATIVE_DOCUMENT_BYTES];
        if(!recovery_json_document(&binding,approved_persistent_binding) ||
           !recovery_field(&binding,0,"installation_identity",native_journal.installation) ||
           !recovery_field(&binding,0,"repository_path",repository_path) ||
           !initialization_reference(&binding,recovery_json_get(&binding,0,"enrollment"),NULL,enrollment))return 0;
        RecoveryJson frozen;
        if(!recovery_json_document(&frozen,enrollment) ||
           !initialization_equal(&frozen,0,&attempt,install))return 0;
    }
    char selected_id[201],referenced[NATIVE_DOCUMENT_BYTES];
    if(!recovery_string(&attempt,recovery_json_get(&attempt,0,"selection"),"identity",selected_id,sizeof(selected_id)) ||
       !recovery_field(&selected,0,"selection_id",selected_id) ||
       !initialization_source_reference(&selected,recovery_json_get(&selected,0,"source_manifest")) ||
       !initialization_reference(&selected,recovery_json_get(&selected,0,"artifact_manifest"),NULL,referenced))return 0;
    int source_ref=recovery_json_get(&selected,0,"source_manifest"),artifact_ref=recovery_json_get(&selected,0,"artifact_manifest"),
        selected_target=recovery_json_get(&selected,0,"target"),selected_decisions=recovery_json_get(&selected,0,"decisions");
    if(!initialization_target(&selected,selected_target) ||
       !recovery_string(&selected,0,"valid_from",stamp,sizeof(stamp)) || initialization_utc(stamp)<0 ||
       !recovery_string(&selected,0,"valid_until",stamp,sizeof(stamp)) || initialization_utc(stamp)<0 ||
       !recovery_string(&selected,source_ref,"sha256",digest,sizeof(digest)) ||
       !recovery_field(&selected,selected_target,"source_manifest_sha256",digest) ||
       !recovery_string(&selected,artifact_ref,"sha256",digest,sizeof(digest)) ||
       !recovery_field(&selected,selected_target,"artifact_manifest_sha256",digest) ||
       selected_decisions<0 || selected.token[selected_decisions].kind!='{' || selected.token[selected_decisions].count!=4 ||
       !initialization_equal(&selected,recovery_json_get(&selected,0,"operational_order"),
           &selected,recovery_json_get(&selected,selected_decisions,"sponsor")))return 0;
    const char *selected_roles[]={"sponsor","ca","pcp","product"};
    for(size_t k=0;k<4;k++)if(!initialization_reference(&selected,recovery_json_get(&selected,selected_decisions,selected_roles[k]),NULL,referenced))return 0;
    char from[80],until[80];
    if(!recovery_string(&selected,0,"valid_from",from,sizeof(from)) ||
       !recovery_string(&selected,0,"valid_until",until,sizeof(until)) ||
       initialization_utc(from)>started_at || initialization_utc(until)<started_at)return 0;
    if(!initialization_reference(&attempt,recovery_json_get(&attempt,0,"operator_order"),NULL,referenced))return 0;
    snprintf(path,sizeof(path),"%s/failed-successor-restore-v1/head-1.json",admission_anchor);
    if(!initialization_reference(&policy,recovery_json_get(&policy,0,"genesis_head"),path,first_raw) ||
       !recovery_json_document(&first,first_raw) || first.token[0].count!=9 ||
       !recovery_field(&first,0,"schema",NATIVE_HEAD_SCHEMA) ||
       !recovery_field(&first,0,"installation_identity",native_journal.installation) ||
       recovery_integer(&first,0,"sequence")!=1 || !recovery_field(&first,0,"state","NATIVE_ACTIVATED") ||
       !recovery_field(&first,0,"incident_id","null") || !recovery_field(&first,0,"active_reservation_id",id) ||
       !recovery_field(&first,0,"previous_head_sha256","0000000000000000000000000000000000000000000000000000000000000000"))return 0;
    snprintf(path,sizeof(path),"%s/failed-successor-restore-v1/%s.json",admission_anchor,id);
    if(!initialization_reference(&policy,recovery_json_get(&policy,0,"genesis_phase"),path,phase_raw) ||
       !recovery_json_document(&phase,phase_raw) || phase.token[0].count!=12 ||
       !recovery_field(&phase,0,"schema",NATIVE_PHASE_SCHEMA) || !recovery_field(&phase,0,"phase","NATIVE_ACTIVATED") ||
       !recovery_field(&phase,0,"identity",id) || !recovery_field(&phase,0,"original_attempt_id",id) ||
       !recovery_field(&phase,0,"installation_identity",native_journal.installation) ||
       !recovery_field(&phase,0,"previous","null") ||
       !initialization_equal(&phase,recovery_json_get(&phase,0,"installation"),&attempt,install) ||
       !initialization_equal(&phase,recovery_json_get(&phase,0,"parent"),&attempt,recovery_json_get(&attempt,0,"parent")) ||
       !initialization_equal(&phase,recovery_json_get(&phase,0,"selection"),&attempt,recovery_json_get(&attempt,0,"selection")) ||
       !initialization_equal(&phase,recovery_json_get(&phase,recovery_json_get(&phase,0,"details"),"initialization_attempt"),
           &policy,recovery_json_get(&policy,0,"attempt")))return 0;
    if(!recovery_string(&phase,0,"recorded_at",stamp,sizeof(stamp)) || initialization_utc(stamp)!=started_at ||
       !recovery_string(&first,0,"recorded_at",stamp,sizeof(stamp)) || initialization_utc(stamp)!=started_at)return 0;
    native_digest(phase_raw,strlen(phase_raw),digest);
    if(!recovery_field(&first,0,"active_reservation_sha256",digest))return 0;
    int enrolled=recovery_json_get(&attempt,0,"predecessor"),details=recovery_json_get(&phase,0,"details");
    if(recovery_field(&attempt,0,"eligibility","COLD_ABSENT")) {
        if(!recovery_field(&attempt,0,"predecessor","null") || !recovery_field(&phase,0,"predecessor","null") ||
           !recovery_field(&phase,details,"enrolled_predecessor","null"))return 0;
    } else if(!recovery_field(&attempt,0,"eligibility","EXISTING_RELEASE_B") || enrolled<0 ||
        attempt.token[enrolled].kind!='{' || attempt.token[enrolled].count!=2 ||
        !initialization_process(&attempt,recovery_json_get(&attempt,enrolled,"process")) ||
        !initialization_equal(&phase,recovery_json_get(&phase,details,"enrolled_predecessor"),&attempt,enrolled) ||
        !initialization_equal(&phase,recovery_json_get(&phase,0,"predecessor"),&attempt,recovery_json_get(&attempt,enrolled,"process")) ||
        !initialization_source_reference(&attempt,recovery_json_get(&attempt,enrolled,"evidence")))return 0;
    if(!initialization_reference(&policy,recovery_json_get(&policy,0,"evidence"),NULL,scratch) ||
       !recovery_json_document(&evidence,scratch) || evidence.token[0].count!=6 ||
       !recovery_field(&evidence,0,"schema","KRONOS_ADMISSION_INITIALIZATION_RESOLUTION_EVIDENCE_V1") ||
       !initialization_equal(&evidence,recovery_json_get(&evidence,0,"attempt"),&policy,recovery_json_get(&policy,0,"attempt")))return 0;
    char evidence_id[201];
    if(!recovery_string(&policy,recovery_json_get(&policy,0,"evidence"),"identity",evidence_id,sizeof(evidence_id)) ||
       !recovery_field(&evidence,0,"identity",evidence_id))return 0;
    /* Evidence parser points into scratch; never overwrite it during reads. */
    char observed[NATIVE_DOCUMENT_BYTES];
    const char *lists[]={"observations","subsequent_observations"};
    for(size_t k=0;k<2;k++) {
        int list=recovery_json_get(&evidence,0,lists[k]);if(list<0 || evidence.token[list].kind!='[')return 0;
        for(int i=list+1;i<evidence.token[list].next;i=evidence.token[i].next)
            if(!initialization_reference(&evidence,i,NULL,observed))return 0;
    }
    if(!setup_genesis_references(&evidence))return 0;
    int unknown=recovery_json_get(&evidence,0,"missing_or_uncertain");
    if(unknown<0 || evidence.token[unknown].kind!='[')return 0;
    for(int i=unknown+1;i<evidence.token[unknown].next;i=evidence.token[i].next)
        if(evidence.token[i].kind!='s' || evidence.token[i].end==evidence.token[i].start)return 0;
    int authority=recovery_json_get(&policy,0,"authority");
    if(authority<0 || policy.token[authority].kind!='{' || policy.token[authority].count!=4)return 0;
    const char *roles[]={"sponsor","ca","pcp","product"};
    for(size_t k=0;k<4;k++)if(!initialization_reference(&policy,recovery_json_get(&policy,authority,roles[k]),NULL,observed))return 0;
    if(!initialization_read(native_journal.root,"admission-head.json",current) || !recovery_json_document(&item,current))return 0;
    long long count=recovery_integer(&item,0,"sequence");if(count<1 || count>1000000000)return 0;
    struct stat exists;snprintf(name,sizeof(name),"head-%lld.json",count+1);
    if(fstatat(native_journal.root,name,&exists,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT)return 0;
    strcpy(previous,"0000000000000000000000000000000000000000000000000000000000000000");
    long long previous_at=-1;
    for(long long n=1;n<=count;n++) {
        snprintf(name,sizeof(name),"head-%lld.json",n);
        if(!initialization_read(native_journal.root,name,retained) || !recovery_json_document(&item,retained) ||
           item.token[0].count!=9 || !recovery_field(&item,0,"schema",NATIVE_HEAD_SCHEMA) ||
           !recovery_field(&item,0,"installation_identity",native_journal.installation) ||
           recovery_integer(&item,0,"sequence")!=n || !recovery_field(&item,0,"previous_head_sha256",previous) ||
           !recovery_string(&item,0,"recorded_at",stamp,sizeof(stamp)))return 0;
        long long at=initialization_utc(stamp);if(at<0 || at<previous_at || (n==1 && strcmp(retained,first_raw)))return 0;
        previous_at=at;native_digest(retained,strlen(retained),previous);
    }
    if(strcmp(retained,current))return 0;
    native_digest(raw,strlen(raw),initialization_disposition_digest);
    return native_root_bound() && validation_permitted();
}
static int native_reload(void) {
    RecoveryJson head;char marker[96],historical[NATIVE_DOCUMENT_BYTES],record[NATIVE_DOCUMENT_BYTES],path[240],digest[65],previous[65],at[64];
    struct stat exists;
    if(!native_root_bound() || !validation_permitted() ||
       !native_read(native_journal.root,"admission-head.json",native_journal.head,sizeof(native_journal.head)) ||
       !recovery_json_document(&head,native_journal.head) || head.token[0].count!=9 ||
       !recovery_field(&head,0,"schema",NATIVE_HEAD_SCHEMA) ||
       !recovery_field(&head,0,"installation_identity",native_journal.installation) ||
       !recovery_string(&head,0,"state",native_journal.state,sizeof(native_journal.state)) ||
       !recovery_string(&head,0,"active_reservation_id",native_journal.identity,sizeof(native_journal.identity)) ||
       !native_identity(native_journal.identity) ||
       !recovery_string(&head,0,"active_reservation_sha256",native_journal.record_digest,65) || !valid_token(native_journal.record_digest) ||
       !recovery_string(&head,0,"previous_head_sha256",previous,sizeof(previous)) || !valid_token(previous) ||
       !recovery_string(&head,0,"recorded_at",at,sizeof(at)) ||
       (native_journal.sequence=recovery_integer(&head,0,"sequence"))<1 || native_journal.sequence>1000000000)return 0;
    if(recovery_field(&head,0,"incident_id","null"))native_journal.incident[0]=0;
    else if(!recovery_string(&head,0,"incident_id",native_journal.incident,sizeof(native_journal.incident)) ||
            !native_identity(native_journal.incident))return 0;
    snprintf(marker,sizeof(marker),"head-%lld.json",native_journal.sequence);
    if(!native_read(native_journal.root,marker,historical,sizeof(historical)) || strcmp(historical,native_journal.head))return 0;
    snprintf(marker,sizeof(marker),"head-%lld.json",native_journal.sequence+1);
    if(fstatat(native_journal.root,marker,&exists,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT)return 0;
    if(native_journal.sequence==1) {
        if(strcmp(native_journal.state,"NATIVE_ACTIVATED") || strcmp(previous,
            "0000000000000000000000000000000000000000000000000000000000000000"))return 0;
    } else {
        snprintf(marker,sizeof(marker),"head-%lld.json",native_journal.sequence-1);
        if(!native_read(native_journal.root,marker,historical,sizeof(historical)))return 0;
        native_digest(historical,strlen(historical),digest);
        if(strcmp(digest,previous))return 0;
    }
    snprintf(path,sizeof(path),"%s.json",native_journal.identity);
    if(!native_read(native_journal.root,path,record,sizeof(record)))return 0;
    native_digest(record,strlen(record),digest);
    if(strcmp(digest,native_journal.record_digest) || !native_head_record_matches(&head,record))return 0;
    native_digest(native_journal.head,strlen(native_journal.head),native_journal.head_digest);
    return native_initialization_admitted() && native_root_bound() && validation_permitted();
}
static int native_open_journal(const char *installation) {
    if(native_journal.root>=0 || !installation || !valid_token(installation) || !admission_still_bound())return 0;
    native_journal.root=openat(admission_descriptor,"failed-successor-restore-v1",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(native_journal.root<0)return 0;
    native_journal.writer=getpid();
    strcpy(native_journal.installation,installation);
    return native_reload();
}
static int native_commit(const char *phase,const char *identity,const char *incident,const char *record) {
    if(!native_identity(phase) || !native_identity(identity) ||
       (incident && *incident && !native_identity(incident)) || !native_reload())return 0;
    RecoveryJson value;if(!recovery_json_document(&value,record))return 0;
    if(!strcmp(phase,"RESTORATION_RESERVED")) {
        if(!recovery_field(&value,0,"schema","KRONOS_FAILED_SUCCESSOR_RESTORATION_RESERVATION_V1") ||
           !recovery_field(&value,0,"reservation_id",identity) ||
           !recovery_field(&value,0,"installation_identity",native_journal.installation) ||
           !incident || !*incident || !recovery_field(&value,0,"incident_id",incident))return 0;
    } else if(!recovery_field(&value,0,"schema",NATIVE_PHASE_SCHEMA) ||
              !recovery_field(&value,0,"identity",identity) || !recovery_field(&value,0,"phase",phase) ||
              !recovery_field(&value,0,"installation_identity",native_journal.installation))return 0;
    char record_digest[65],head[NATIVE_DOCUMENT_BYTES],stamp[64],date[32],marker[96],next[96],path[240],selected[65];
    struct timespec now;struct tm utc;
    if(clock_gettime(CLOCK_REALTIME,&now)!=0 || !gmtime_r(&now.tv_sec,&utc) ||
       !strftime(date,sizeof(date),"%Y-%m-%dT%H:%M:%S",&utc))return 0;
    snprintf(stamp,sizeof(stamp),"%s.%06ld+00:00",date,now.tv_nsec/1000);
    native_digest(record,strlen(record),record_digest);strcpy(selected,native_journal.head_digest);
    char incident_json[208];
    if(incident && *incident)snprintf(incident_json,sizeof(incident_json),"\"%s\"",incident);
    else strcpy(incident_json,"null");
    int n=snprintf(head,sizeof(head),"{\"active_reservation_id\":\"%s\",\"active_reservation_sha256\":\"%s\",\"incident_id\":%s,\"installation_identity\":\"%s\",\"previous_head_sha256\":\"%s\",\"recorded_at\":\"%s\",\"schema\":\"%s\",\"sequence\":%lld,\"state\":\"%s\"}",
        identity,record_digest,incident_json,native_journal.installation,selected,stamp,NATIVE_HEAD_SCHEMA,native_journal.sequence+1,phase);
    if(n<1 || (size_t)n>=sizeof(head))return 0;
    snprintf(marker,sizeof(marker),"head-%lld.json",native_journal.sequence+1);
    snprintf(next,sizeof(next),"head-%lld.next",native_journal.sequence+1);
    snprintf(path,sizeof(path),"%s.json",identity);
    /* Intent precedes every record/rename. A crash at any later point leaves
     * either an unselected next-head intent or a selected unresolved phase. */
    if(!native_exclusive(marker,head) || !native_exclusive(path,record) ||
       !native_exclusive(next,head) || !native_root_bound() || !validation_permitted())return 0;
    char current[NATIVE_DOCUMENT_BYTES],actual[65];
    if(!native_read(native_journal.root,"admission-head.json",current,sizeof(current)))return 0;
    native_digest(current,strlen(current),actual);
    if(strcmp(actual,selected) || renameat(native_journal.root,next,native_journal.root,"admission-head.json")!=0 ||
       fsync(native_journal.root)!=0 || !native_reload())return 0;
    return !strcmp(native_journal.identity,identity) && !strcmp(native_journal.state,phase);
}

typedef struct {
    int active,restoration,cleanup_terminal,terminal_attempted;
    pid_t parent;
    char repository[PATH_MAX],python[PATH_MAX],mode[64],parent_birth[65];
    char selected[PATH_MAX+400],current_record[201],original[201];
    char last_result[NATIVE_DOCUMENT_BYTES];
} NativeStartupContext;
static NativeStartupContext native_startup={0};

static int native_birth_digest(unsigned long long seconds,unsigned long long micros,char out[65]) {
    if(!seconds || micros>=1000000 || seconds>(ULLONG_MAX-micros)/1000000)return 0;
    char value[64];int n=snprintf(value,sizeof(value),"%llu",seconds*1000000+micros);
    if(n<1 || (size_t)n>=sizeof(value))return 0;native_digest(value,(size_t)n,out);return 1;
}
static int native_process_birth(pid_t pid,char out[65]) {
    struct proc_bsdinfo info;memset(&info,0,sizeof(info));
    return pid>1 && proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&info,sizeof(info))==(int)sizeof(info) &&
        info.pbi_pid==(uint32_t)pid && native_birth_digest(info.pbi_start_tvsec,info.pbi_start_tvusec,out);
}
static int native_json_text(const char *text) {
    if(!text)return 0;
    for(const unsigned char *p=(const unsigned char*)text;*p;p++)
        if(*p<32 || *p>=127 || *p=='"' || *p=='\\')return 0;
    return 1;
}
static int native_copy_json(const RecoveryJson *j,int token,char *out,size_t capacity) {
    if(token<0 || (j->token[token].kind!='{' && j->token[token].kind!='['))return 0;
    int length=j->token[token].end-j->token[token].start;
    if(length<2 || (size_t)length>=capacity)return 0;
    memcpy(out,j->text+j->token[token].start,(size_t)length);out[length]=0;return 1;
}
static int native_select_installed(void);
static int native_select_environment(void) {
    if(!strcmp(native_startup.mode,"ORDINARY") || !strcmp(native_startup.mode,"ORDINARY_STOP"))return native_select_installed();
    const char *path=getenv("KRONOS_NATIVE_SELECTION_PATH"),*bytes=getenv("KRONOS_NATIVE_SELECTION_BYTES"),
        *hash=getenv("KRONOS_NATIVE_SELECTION_SHA256"),*identity=getenv("KRONOS_NATIVE_SELECTION_ID");
    if(!path || path[0]!='/' || !native_json_text(path) || !bytes || !*bytes ||
       strspn(bytes,"0123456789")!=strlen(bytes) || strlen(bytes)>5 ||
       atol(bytes)<1 || atol(bytes)>65536 || !hash || !valid_token(hash) || !native_identity(identity))return 0;
    int n=snprintf(native_startup.selected,sizeof(native_startup.selected),
        "{\"bytes\":%ld,\"identity\":\"%s\",\"path\":\"%s\",\"sha256\":\"%s\"}",atol(bytes),identity,path,hash);
    return n>0 && (size_t)n<sizeof(native_startup.selected);
}
/* ORDER 83553: null is an explicit disabled status, never missing metadata.
 * Compare all source pins and the actual original boot before any proposal is
 * accepted, including prepare-only initialization. No budget is reacquired. */
static int native_helper_pin_matches(const RecoveryJson *result,const char *field,const char *pin) {
    if(!pin)return recovery_field(result,0,field,"null");
    char digest[65];native_digest(pin,strlen(pin),digest);
    return recovery_field(result,0,field,digest);
}
static int native_helper_agreement(const RecoveryJson *result) {
    return native_helper_pin_matches(result,"initialization_disposition_sha256",initialization_policy()) &&
        native_helper_pin_matches(result,"persistent_binding_sha256",approved_persistent_binding) &&
        native_helper_pin_matches(result,"ordinary_policy_sha256",approved_ordinary_restart_policy) &&
        recovery_field(result,0,"boot_session",operation_boot_identity) &&
        admission_still_bound() && validation_permitted();
}
static int native_validation(const char *action,const char *identity,const char *details,int selected) {
    char input[NATIVE_DOCUMENT_BYTES];
    if(native_startup.parent!=getpid() || !native_json_text(action) || !native_json_text(identity) ||
       !native_json_text(native_startup.repository) || !native_json_text(canonical_bundle) ||
       !native_json_text(admission_anchor) || !admission_still_bound() || !validation_permitted())return 0;
    int n=snprintf(input,sizeof(input),
        "{\"action\":\"%s\",\"anchor\":\"%s\",\"attempt_deadline_ns\":%lld,\"bundle\":\"%s\",\"details\":%s,\"identity\":\"%s\",\"mode\":\"%s\",\"parent_birth\":\"%s\",\"parent_pid\":%ld,\"repository\":\"%s\",\"selected\":%s}",
        action,admission_anchor,validation_current_deadline(),canonical_bundle,details,identity,native_startup.mode,native_startup.parent_birth,
        (long)getpid(),native_startup.repository,selected?native_startup.selected:"null");
    if(n<1 || (size_t)n>=sizeof(input))return 0;
    char *arguments[]={native_startup.python,"-B","-c",
        "from kronos.common.legacy_bootstrap import native_validation_stdio; native_validation_stdio()",NULL};
    if(!bounded_validation_cli(native_startup.repository,native_startup.python,arguments,input,
        native_startup.last_result,sizeof(native_startup.last_result),0,"NATIVE_ADMISSION",20))return 0;
    RecoveryJson result;
    if(!recovery_json_document(&result,native_startup.last_result) ||
       !native_helper_agreement(&result))return 0;
    if(!strcmp(native_startup.mode,"ADMISSION_HEAD_INITIALIZATION"))
        return (!strcmp(action,"initialization-prepare") || !strcmp(action,"initialization-recheck")) &&
            recovery_field(&result,0,"disposition","PREPARED_PENDING_EXACT_ADMISSION_REVIEW");
    if(!strcmp(native_startup.mode,"CONTROLLED_INSTALLATION_SETUP"))
        return ((!strcmp(action,"setup-prepare") || !strcmp(action,"setup-verify-prepared")) &&
            (recovery_field(&result,0,"disposition","PREPARATION_ONLY_PENDING_EXACT_REVIEW") ||
             recovery_field(&result,0,"disposition","PREPARED_ACTIVATION_UNPROVED")));
    /* Matched disabled metadata permits preparation, never operational
     * admission without the existing separately pinned genesis disposition. */
    return initialization_policy()!=NULL;
}
static int native_gate(const char *repository,const char *python,const char *mode) {
    if(!repository || !python || strlen(repository)>=sizeof(native_startup.repository) ||
       strlen(python)>=sizeof(native_startup.python) || !mode || strlen(mode)>=sizeof(native_startup.mode))return 0;
    strcpy(native_startup.repository,repository);strcpy(native_startup.python,python);strcpy(native_startup.mode,mode);
    native_startup.parent=getpid();
    if(!native_process_birth(getpid(),native_startup.parent_birth) || !native_validation("gate","","{}",0))return 0;
    RecoveryJson result;char installation[65],head_digest[65];
    if(!recovery_json_document(&result,native_startup.last_result) ||
       !recovery_string(&result,recovery_json_get(&result,0,"installation"),"identity",installation,sizeof(installation)) ||
       !recovery_string(&result,recovery_json_get(&result,0,"head"),"sha256",head_digest,sizeof(head_digest)) ||
       !native_open_journal(installation) || strcmp(head_digest,native_journal.head_digest))return 0;
    return 1;
}
static int native_apply_proposal(void) {
    RecoveryJson result;char phase[64],identity[201],incident[201]={0},record[NATIVE_DOCUMENT_BYTES],expected[65];
    if(!recovery_json_document(&result,native_startup.last_result) ||
       !native_helper_agreement(&result) ||
       !recovery_string(&result,0,"phase",phase,sizeof(phase)) ||
       !recovery_string(&result,0,"identity",identity,sizeof(identity)) ||
       !recovery_string(&result,recovery_json_get(&result,0,"head"),"sha256",expected,sizeof(expected)) ||
       !native_copy_json(&result,recovery_json_get(&result,0,"record"),record,sizeof(record)) ||
       (!recovery_field(&result,0,"incident_id","null") &&
        !recovery_string(&result,0,"incident_id",incident,sizeof(incident))) ||
       !native_reload() || strcmp(expected,native_journal.head_digest))return 0;
    /* Any partial auxiliary publication remains exclusive and blocks this
     * deterministic transition on the next invocation; never replace it. */
    int documents=recovery_json_get(&result,0,"documents");
    if(documents>=0) {
        if(result.token[documents].kind!='[')return 0;
        for(int i=documents+1;i<result.token[documents].next;i=result.token[i].next) {
            char document[NATIVE_DOCUMENT_BYTES],name[240],id[201],digest[65],expected_digest[65];
            int reference=recovery_json_get(&result,i,"reference");
            if(result.token[i].kind!='{' || !recovery_string(&result,reference,"identity",id,sizeof(id)) ||
               !native_identity(id) || !recovery_string(&result,reference,"sha256",expected_digest,65) ||
               !native_copy_json(&result,recovery_json_get(&result,i,"document"),document,sizeof(document)))return 0;
            native_digest(document,strlen(document),digest);
            snprintf(name,sizeof(name),"%s.json",id);
            if(strcmp(digest,expected_digest) || !native_exclusive(name,document))return 0;
        }
    }
    if(!native_commit(phase,identity,incident,record))return 0;
    if(!recovery_string(&result,0,"original_attempt_id",native_startup.original,sizeof(native_startup.original)))return 0;
    strcpy(native_startup.current_record,identity);native_startup.active=1;return 1;
}

static int recovery_control_record(const char *path,pid_t *pid,char token[65]) {
    char raw[256],expected[256];long parsed=0;char proof[65]={0};
    if(!recovery_read_file(path,raw,sizeof(raw),1) ||
       sscanf(raw,"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%64[0-9a-f]",&parsed,proof)!=2 ||
       parsed<2 || parsed>INT_MAX || !valid_token(proof))return 0;
    snprintf(expected,sizeof(expected),"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%s\n",parsed,proof);
    if(strcmp(raw,expected)){memset(proof,0,sizeof(proof));return 0;}
    *pid=(pid_t)parsed;memcpy(token,proof,65);memset(proof,0,sizeof(proof));return 1;
}

static int native_startup_active(void) { return native_startup.active; }
static int native_reference(const char *path,const char *identity,char *out,size_t capacity) {
    char parent[PATH_MAX],raw[NATIVE_DOCUMENT_BYTES],digest[65];
    if(!path || !native_json_text(path) || !native_identity(identity) ||
       strlen(path)>=sizeof(parent) || !recovery_safe_path(path,0,1))return 0;
    strcpy(parent,path);char *name=strrchr(parent,'/');if(!name || !name[1])return 0;*name++=0;
    int directory=open(parent,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(directory<0)return 0;
    int ok=native_read(directory,name,raw,sizeof(raw));close(directory);if(!ok)return 0;
    native_digest(raw,strlen(raw),digest);
    int n=snprintf(out,capacity,"{\"bytes\":%zu,\"identity\":\"%s\",\"path\":\"%s\",\"sha256\":\"%s\"}",
        strlen(raw),identity,path,digest);
    return n>0 && (size_t)n<capacity;
}
static int native_current_reference(char *out,size_t capacity) {
    char path[PATH_MAX];
    if(!native_reload() || snprintf(path,sizeof(path),"%s/failed-successor-restore-v1/%s.json",
        admission_anchor,native_journal.identity)>=(int)sizeof(path))return 0;
    return native_reference(path,native_journal.identity,out,capacity);
}
static int native_original_reserve(pid_t predecessor) {
    char details[512],birth[65],identity[100];unsigned char random[24];
    arc4random_buf(random,sizeof(random));strcpy(identity,"original-");
    for(size_t i=0;i<sizeof(random);i++)snprintf(identity+9+2*i,3,"%02x",random[i]);
    if(predecessor>1) {
        if(!native_process_birth(predecessor,birth))return 0;
        snprintf(details,sizeof(details),"{\"predecessor\":{\"kernel_birth\":\"%s\",\"pid\":%ld}}",birth,(long)predecessor);
    } else strcpy(details,"{\"predecessor\":null}");
    return native_select_environment() && native_validation("original-reserve",identity,details,1) && native_apply_proposal();
}

/* Native current durability belongs to the new attempt. Python remains a
 * read-only planner/validator. No old outcome or receipt is rewritten. */
static int ordinary_durable_file(const RecoveryJson *plan,int ref) {
    char path[PATH_MAX],expected[65],copy[PATH_MAX];long long size=recovery_integer(plan,ref,"bytes");
    long long mode=recovery_integer(plan,ref,"mode");
    if(ref<0 || plan->token[ref].kind!='{' || plan->token[ref].count!=5 || size<0 ||
       mode<0 || mode>0777 || (mode&0022) || !recovery_string(plan,ref,"path",path,sizeof(path)) ||
       path[0]!='/' || !native_json_text(path) || !recovery_string(plan,ref,"sha256",expected,65) || !valid_token(expected))return 0;
    strcpy(copy,path);char *last=strrchr(copy,'/');if(!last || !last[1])return 0;*last++=0;
    int directory=open("/",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(directory<0)return 0;
    char *state=NULL;int ok=1;
    for(char *part=strtok_r(copy,"/",&state);part;part=strtok_r(NULL,"/",&state)) {
        if(!strcmp(part,".") || !strcmp(part,"..") || !validation_permitted()){ok=0;break;}
        int next=openat(directory,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        if(close(directory)!=0)ok=0;directory=next;
        struct stat metadata;if(directory<0 || fstat(directory,&metadata)!=0 ||
            (metadata.st_uid!=0 && metadata.st_uid!=getuid()) || (metadata.st_mode&0022)){ok=0;break;}
    }
    if(!strcmp(last,".") || !strcmp(last,".."))ok=0;
    int fd=ok?openat(directory,last,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC):-1;
    struct stat before,after,named;CC_SHA256_CTX context;CC_SHA256_Init(&context);
    if(fd<0 || fstat(fd,&before)!=0 || !S_ISREG(before.st_mode) || before.st_uid!=getuid() ||
       (before.st_mode&0777)!=mode || before.st_size!=size)ok=0;
    unsigned char buffer[65536],hash[32];long long used=0;
    while(ok) {
        if(!validation_permitted() || !admission_still_bound()){ok=0;break;}
        ssize_t n=read(fd,buffer,sizeof(buffer));if(n<0 && errno==EINTR)continue;
        if(n<0){ok=0;break;}if(!n)break;used+=n;if(used>size){ok=0;break;}
        CC_SHA256_Update(&context,buffer,(CC_LONG)n);
    }
    CC_SHA256_Final(hash,&context);char digest[65];for(int i=0;i<32;i++)snprintf(digest+2*i,3,"%02x",hash[i]);
    if(ok)ok=used==size && !strcmp(digest,expected) && fsync(fd)==0 &&
        fstat(fd,&after)==0 && fstatat(directory,last,&named,AT_SYMLINK_NOFOLLOW)==0 &&
        native_same_file(&before,&after) && native_same_file(&after,&named) && fsync(directory)==0;
    if(fd>=0 && close(fd)!=0)ok=0;if(directory>=0 && close(directory)!=0)ok=0;
    return ok && validation_permitted() && admission_still_bound();
}
static int recovery_listener_scan(pid_t pid,int absent);
static int initialization_process_inventory(pid_t enrolled);
static int native_ordinary_current_durable(void) {
    if(!native_validation("ordinary-durability-plan","","{}",1))return 0;
    RecoveryJson result;char expected[65];
    if(!recovery_json_document(&result,native_startup.last_result) ||
       !recovery_string(&result,recovery_json_get(&result,0,"head"),"sha256",expected,sizeof(expected)) ||
       !native_reload() || strcmp(expected,native_journal.head_digest))return 0;
    int list=recovery_json_get(&result,0,"durability_plan");if(list<0 || result.token[list].kind!='[')return 0;
    for(int item=list+1;item<result.token[list].next;item=result.token[item].next)
        if(!ordinary_durable_file(&result,item))return 0;
    int chunks=recovery_json_get(&result,0,"durability_chunks");
    if(chunks<0 || result.token[chunks].kind!='[' || result.token[chunks].count>128)return 0;
    if(result.token[chunks].count) {
        char control[PATH_MAX];snprintf(control,sizeof(control),"%s/browser-backend-v1.control",admission_anchor);
        if(!initialization_process_inventory(0) || !recovery_listener_scan(0,1) ||
           !cold_start_has_no_control_or_live_handoff(control))return 0;
    }
    for(int item=chunks+1;item<result.token[chunks].next;item=result.token[item].next) {
        char raw[NATIVE_DOCUMENT_BYTES],path[PATH_MAX],identity[201],digest[65],reference[PATH_MAX+400];RecoveryJson chunk,ref;
        if(!ordinary_durable_file(&result,item) ||
           !recovery_string(&result,item,"path",path,sizeof(path)) || !native_json_text(path) ||
           !recovery_string(&result,item,"identity",identity,sizeof(identity)) || !native_identity(identity) ||
           !recovery_string(&result,item,"sha256",digest,sizeof(digest)) || !valid_token(digest))return 0;
        int n=snprintf(reference,sizeof(reference),"{\"bytes\":%lld,\"identity\":\"%s\",\"path\":\"%s\",\"sha256\":\"%s\"}",
            recovery_integer(&result,item,"bytes"),identity,path,digest);
        if(n<1 || (size_t)n>=sizeof(reference) || !recovery_json_document(&ref,reference) ||
           !initialization_reference(&ref,0,NULL,raw) ||
           !recovery_json_document(&chunk,raw) || chunk.token[0].count!=3 ||
           !recovery_field(&chunk,0,"schema","KRONOS_PREPARED_ACTIVATION_FILES_V1"))return 0;
        int files=recovery_json_get(&chunk,0,"files");
        if(files<0 || chunk.token[files].kind!='[' || chunk.token[files].count<1 || chunk.token[files].count>128)return 0;
        for(int row=files+1;row<chunk.token[files].next;row=chunk.token[row].next) {
            char original[NATIVE_DOCUMENT_BYTES],planned[NATIVE_DOCUMENT_BYTES];RecoveryJson entry;
            if(chunk.token[row].kind!='{' || chunk.token[row].count!=4 ||
               !native_copy_json(&chunk,row,original,sizeof(original)))return 0;
            int n=snprintf(planned,sizeof(planned),"{\"identity\":\"retained-activation-state\",%s",original+1);
            if(n<1 || (size_t)n>=sizeof(planned) || !recovery_json_document(&entry,planned) ||
               !ordinary_durable_file(&entry,0))return 0;
        }
    }
    return native_root_bound() && validation_permitted();
}

static int native_advance(const char *phase,const char *observed) {
    if(!strcmp(native_startup.mode,"ORDINARY") && !strcmp(phase,"CHILD_START_RESERVED") &&
       !native_ordinary_current_durable())return 0;
    char details[NATIVE_DOCUMENT_BYTES];
    int n=snprintf(details,sizeof(details),"{\"observed\":%s,\"phase\":\"%s\"}",observed,phase);
    return n>0 && (size_t)n<sizeof(details) && native_validation("original-advance","",details,1) && native_apply_proposal();
}
static int native_dispatch_intent(const char *control,const char *generation) {
    char reference[PATH_MAX+400],observed[PATH_MAX+600];
    if(!native_reference(control,"predecessor-control",reference,sizeof(reference)))return 0;
    snprintf(observed,sizeof(observed),"{\"control\":%s,\"generation\":\"%s\"}",reference,generation);
    return native_advance("SHUTDOWN_DISPATCH_INTENT",observed);
}
static int native_retired(const char *home,const char *generation) {
    char path[PATH_MAX],reference[PATH_MAX+400],observed[PATH_MAX+600];
    if(snprintf(path,sizeof(path),"%s/Library/Application Support/KRONOS/runtime/maintenance/%s.json",home,generation)>=(int)sizeof(path) ||
       !native_reference(path,generation,reference,sizeof(reference)))return 0;
    snprintf(observed,sizeof(observed),"{\"handoff\":%s,\"listener_absent\":true,\"shutdown_accepted\":true}",reference);
    return native_advance("PREDECESSOR_RETIRED",observed);
}
static int native_identify_child(pid_t child) {
    char selected[PATH_MAX+400],record[NATIVE_DOCUMENT_BYTES],name[240],birth[65],parent[1024];RecoveryJson j;
    if(!native_current_reference(selected,sizeof(selected)) || !native_process_birth(child,birth))return 0;
    snprintf(name,sizeof(name),"%s.json",native_journal.identity);
    if(!native_read(native_journal.root,name,record,sizeof(record)) || !recovery_json_document(&j,record) ||
       !native_copy_json(&j,recovery_json_get(&j,0,"parent"),parent,sizeof(parent)))return 0;
    char identified[NATIVE_DOCUMENT_BYTES];
    int n=snprintf(identified,sizeof(identified),"{\"child\":{\"kernel_birth\":\"%s\",\"pid\":%ld},\"parent\":%s,\"schema\":\"KRONOS_NATIVE_CHILD_IDENTIFIED_V1\",\"selected\":%s}",
        birth,(long)child,parent,selected);
    snprintf(name,sizeof(name),"%s.identified.json",native_journal.identity);
    return n>0 && (size_t)n<sizeof(identified) && native_exclusive(name,identified);
}
static int native_env_reference(const RecoveryJson *j,int object,const char *prefix) {
    char key[100],text[PATH_MAX+1];
    const char *fields[]={"path","sha256","identity"};const char *suffix[]={"PATH","SHA256","ID"};
    for(int i=0;i<3;i++) {
        snprintf(key,sizeof(key),"%s_%s",prefix,suffix[i]);
        if(!recovery_string(j,object,fields[i],text,sizeof(text)) || setenv(key,text,1)!=0)return 0;
    }
    long long size=recovery_integer(j,object,"bytes");
    if(size<1 || size>8*1024*1024)return 0;
    snprintf(key,sizeof(key),"%s_BYTES",prefix);snprintf(text,sizeof(text),"%lld",size);
    return setenv(key,text,1)==0;
}
static int native_child_environment(void) {
    char selected[PATH_MAX+400];RecoveryJson j;
    if(!native_current_reference(selected,sizeof(selected)) || !recovery_json_document(&j,selected) ||
       !native_env_reference(&j,0,"KRONOS_NATIVE_ATTEMPT") ||
       setenv("KRONOS_NATIVE_HEAD_SHA256",native_journal.head_digest,1)!=0)return 0;
    if(native_startup.restoration) {
        RecoveryJson proposal;char text[PATH_MAX+1];
        if(!recovery_json_document(&proposal,native_startup.last_result))return 0;
        int selection=recovery_json_get(&proposal,0,"selection");
        if(!native_env_reference(&proposal,recovery_json_get(&proposal,selection,"permit"),"KRONOS_RESTORATION_PERMIT") ||
           !native_env_reference(&j,0,"KRONOS_RESTORATION_RESERVATION") ||
           setenv("KRONOS_RESTORATION_ORIGINAL_ATTEMPT_ID",native_startup.original,1)!=0)return 0;
        for(int i=0;i<2;i++) {
            int manifest=recovery_json_get(&proposal,selection,i?"artifact_manifest":"source_manifest");
            if(!recovery_string(&proposal,manifest,"path",text,sizeof(text)) ||
               setenv(i?"KRONOS_RESTORATION_ARTIFACT_MANIFEST_PATH":"KRONOS_RESTORATION_SOURCE_MANIFEST_PATH",text,1)!=0)return 0;
        }
        if(setenv("KRONOS_RESTORATION_PARENT_KERNEL_BIRTH",native_startup.parent_birth,1)!=0)return 0;
    }
    return 1;
}
static int native_terminal_cleanup(void) {
    if(native_startup.cleanup_terminal)return 1;
    if(native_startup.terminal_attempted || !admission_child_observed ||
       !WIFEXITED(admission_child_status) || WEXITSTATUS(admission_child_status)!=78 || validation_has_unresolved())return 0;
    native_startup.terminal_attempted=1;
    char details[256];snprintf(details,sizeof(details),
        "{\"child_pid\":%ld,\"exit_code\":78,\"terminal_reaped\":true}",(long)admission_child);
    if(!native_validation("child-exited","",details,1) || !native_apply_proposal())return 0;
    native_startup.cleanup_terminal=1;return 1;
}
static int recovery_listener_owner(pid_t pid);
static int native_ready(void) {
    if(!validation_permitted())return 0;
    char name[240];struct stat st;
    snprintf(name,sizeof(name),"%s.startup-success.json",native_startup.current_record);
    /* Do not spawn a validation helper for facts still being produced. A helper
     * rejection is terminal, not a polling/retry protocol. */
    if(fstatat(native_journal.root,name,&st,AT_SYMLINK_NOFOLLOW)!=0)return 0;
    if(!backend_is_ready() || !recovery_listener_owner(admission_child))return 0;
    char response[BACKEND_STATUS_RESPONSE_BYTES],control[PATH_MAX],reference[PATH_MAX+400],details[NATIVE_DOCUMENT_BYTES];
    const char *home=getenv("HOME");pid_t pid=0;char token[65];
    if(!home || snprintf(control,sizeof(control),"%s/Library/Application Support/KRONOS/runtime/browser-backend-v1.control",home)>=(int)sizeof(control) ||
       !recovery_control_record(control,&pid,token) || pid!=admission_child ||
       !native_reference(control,"actual-ready-control",reference,sizeof(reference)) ||
       !read_backend_route("/runtime/status",response))return 0;
    memset(token,0,sizeof(token));const char *body=strstr(response,"\r\n\r\n");if(!body)return 0;body+=4;
    /* Keep the exact HTTP observation inside a canonical request envelope.
     * The server's object insertion order is not a canonical document order. */
    char runtime_hex[BACKEND_STATUS_RESPONSE_BYTES*2+1];
    size_t body_size=strlen(body);if(body_size>=BACKEND_STATUS_RESPONSE_BYTES)return 0;
    const char *hex="0123456789abcdef";
    for(size_t i=0;i<body_size;i++) {
        unsigned char value=(unsigned char)body[i];
        runtime_hex[2*i]=hex[value>>4];runtime_hex[2*i+1]=hex[value&15];
    }
    runtime_hex[2*body_size]=0;
    int n=snprintf(details,sizeof(details),"{\"child_pid\":%ld,\"control\":%s,\"listener_owned\":true,\"runtime_json_hex\":\"%s\"}",
        (long)admission_child,reference,runtime_hex);
    return n>0 && (size_t)n<sizeof(details) && native_validation("child-ready","",details,1) && native_apply_proposal();
}
static int native_reuse(const char *control) {
    char record[NATIVE_DOCUMENT_BYTES],name[240],birth[65],expected_birth[65],revision[65],actual[41];
    char response[BACKEND_STATUS_RESPONSE_BYTES],token[65];pid_t pid=0;RecoveryJson j;
    if(!native_reload() || (strcmp(native_journal.state,"READY_COMPLETE") && strcmp(native_journal.state,"NATIVE_ACTIVATED")) ||
       !backend_is_reusable(control) || !recovery_control_record(control,&pid,token) ||
       !recovery_listener_owner(pid) || !native_process_birth(pid,birth))return 0;
    memset(token,0,sizeof(token));snprintf(name,sizeof(name),"%s.json",native_journal.identity);
    if(!native_read(native_journal.root,name,record,sizeof(record)) || !recovery_json_document(&j,record))return 0;
    int child=recovery_json_get(&j,recovery_json_get(&j,0,"details"),"child");
    return recovery_integer(&j,child,"pid")==pid &&
        recovery_string(&j,child,"kernel_birth",expected_birth,sizeof(expected_birth)) && !strcmp(birth,expected_birth) &&
        recovery_string(&j,child,"revision",revision,sizeof(revision)) &&
        read_backend_route("/runtime/status",response) && runtime_process_revision(response,pid,actual) &&
        !strcmp(revision,actual) && admission_still_bound() && validation_permitted();
}

typedef struct RecoveryAuthorization {
    char attempt[65],file[PATH_MAX],root[PATH_MAX],digest[65],maintenance[65];
    char predecessor[41],successor[41],control_digest[65],package[65];
    char rollback[PATH_MAX],rollback_identity[65],relation[PATH_MAX],diagnosis[PATH_MAX];
    char sponsor[PATH_MAX],sponsor_digest[65],control[PATH_MAX];
    long long valid_from,valid_until,reserved_at;pid_t pid;int historical, swing_incident;char artifact_receipt_digest[65];
} RecoveryAuthorization;

static int recovery_time_valid(const RecoveryAuthorization *a,long long now) {
    if(now<a->valid_from || now>=a->valid_until)return 0;
    return (a->historical || a->swing_incident) ? (a->valid_from>=RECOVERY_END_US && now>=RECOVERY_END_US &&
        a->valid_until-a->valid_from<=RECOVERY_HISTORY_MAX_VALIDITY_US) :
        (a->valid_until<=RECOVERY_END_US && now>=RECOVERY_START_US && now<RECOVERY_END_US);
}
static const char *recovery_capability(const RecoveryAuthorization *a) {
    return a->historical?RECOVERY_HISTORY_CAPABILITY:RECOVERY_CAPABILITY;
}
static const char *recovery_relation(const RecoveryAuthorization *a) {
    return a->swing_incident?a->artifact_receipt_digest:(a->historical?RECOVERY_HISTORY_RELATION:RECOVERY_RELATION);
}
static const char *recovery_diagnosis(const RecoveryAuthorization *a) {
    return a->swing_incident?RECOVERY_SWING_DIAGNOSIS:(a->historical?RECOVERY_HISTORY_DIAGNOSIS:RECOVERY_DIAGNOSIS);
}

static int recovery_swing_process_start(pid_t pid) {
    struct proc_bsdinfo info;
    return pid==RECOVERY_SWING_PID &&
        proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&info,sizeof(info))==(int)sizeof(info) &&
        (long long)info.pbi_start_tvsec*1000000+info.pbi_start_tvusec==RECOVERY_SWING_START_US;
}
static int recovery_swing_authorization(const RecoveryJson *j,const char *raw,const char *control,
                                       pid_t pid,const char *target,long long now,RecoveryAuthorization *a) {
    char reference[256],actual[65];
    a->swing_incident=1;
    if(j->token[0].count!=23 || pid!=RECOVERY_SWING_PID || !strcmp(target,RECOVERY_SWING_PREDECESSOR) ||
       !recovery_field(j,0,"recovery_class",RECOVERY_CLASS) || !recovery_field(j,0,"state","SPONSOR_APPROVED") ||
       !recovery_field(j,0,"attempt_identity",a->attempt) ||
       !recovery_field(j,0,"predecessor_revision",RECOVERY_SWING_PREDECESSOR) ||
       !recovery_field(j,0,"successor_revision",target) || recovery_integer(j,0,"predecessor_pid")!=pid ||
       recovery_integer(j,0,"predecessor_start_us")!=RECOVERY_SWING_START_US ||
       !recovery_field(j,0,"predecessor_maintenance_identity",RECOVERY_SWING_GENERATION) ||
       !recovery_field(j,0,"predecessor_package_identity",RECOVERY_SWING_PACKAGE) ||
       !recovery_field(j,0,"rollback_package_identity",RECOVERY_SWING_PACKAGE) ||
       !recovery_field(j,0,"diagnosis_sha256",RECOVERY_SWING_DIAGNOSIS) ||
       !recovery_string(j,0,"sponsor_authorization_reference",reference,sizeof(reference)) ||
       !recovery_string(j,0,"sponsor_authorization_path",a->sponsor,sizeof(a->sponsor)) ||
       !recovery_string(j,0,"sponsor_authorization_sha256",a->sponsor_digest,sizeof(a->sponsor_digest)) ||
       !valid_token(a->sponsor_digest) || !recovery_file_digest(a->sponsor,actual,0) || strcmp(actual,a->sponsor_digest) ||
       !recovery_string(j,0,"private_control_sha256",a->control_digest,sizeof(a->control_digest)) ||
       !recovery_file_digest(control,actual,1) || strcmp(actual,a->control_digest) ||
       !recovery_string(j,0,"installed_package_identity",a->package,sizeof(a->package)) ||
       !valid_token(a->package) || !strcmp(a->package,RECOVERY_SWING_PACKAGE) ||
       !recovery_string(j,0,"rollback_bundle",a->rollback,sizeof(a->rollback)) ||
       !recovery_separate_bundle(a->rollback,canonical_bundle) ||
       !recovery_string(j,0,"stage_a_receipt_path",a->relation,sizeof(a->relation)) ||
       !recovery_string(j,0,"stage_a_receipt_sha256",a->artifact_receipt_digest,sizeof(a->artifact_receipt_digest)) ||
       !valid_token(a->artifact_receipt_digest) || !recovery_file_digest(a->relation,actual,1) ||
       strcmp(actual,a->artifact_receipt_digest) ||
       !recovery_string(j,0,"diagnosis_path",a->diagnosis,sizeof(a->diagnosis)) ||
       !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,RECOVERY_SWING_DIAGNOSIS) ||
       !recovery_file_digest(a->file,a->digest,1))return 0;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];char hex[65];
    CC_SHA256(raw,(CC_LONG)strlen(raw),digest);
    for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
    a->valid_from=recovery_integer(j,0,"valid_from_us");a->valid_until=recovery_integer(j,0,"valid_until_us");
    if(strcmp(hex,a->digest) || a->valid_from<=RECOVERY_SWING_START_US ||
       a->valid_until<=a->valid_from || !recovery_time_valid(a,now))return 0;
    a->pid=pid;strcpy(a->predecessor,RECOVERY_SWING_PREDECESSOR);strcpy(a->successor,target);
    strcpy(a->maintenance,RECOVERY_SWING_GENERATION);strcpy(a->rollback_identity,RECOVERY_SWING_PACKAGE);
    strcpy(a->control,control);return 1;
}

static int recovery_load_authorization(const char *root,const char *attempt,
                                      const char *control,pid_t pid,const char *target,
                                      long long now,RecoveryAuthorization *a) {
    if(!valid_token(attempt) || !valid_revision(target) || pid<2 ||
       !recovery_safe_path(root,1,1))return 0;
    memset(a,0,sizeof(*a));strcpy(a->root,root);strcpy(a->attempt,attempt);
    if(snprintf(a->file,sizeof(a->file),"%s/%s.authorization.json",root,attempt)>=(int)sizeof(a->file))return 0;
    char raw[16384],reference[256],sponsor_path[PATH_MAX],sponsor_hash[65],actual[65];RecoveryJson j;
    if(!recovery_read_file(a->file,raw,sizeof(raw),1) || !recovery_json_document(&j,raw))return 0;
    if(recovery_field(&j,0,"schema",RECOVERY_SWING_SCHEMA))
        return recovery_swing_authorization(&j,raw,control,pid,target,now,a);
    a->historical=recovery_field(&j,0,"schema",RECOVERY_HISTORY_SCHEMA);
    if((a->historical ? (j.token[0].count!=25 ||
            !recovery_field(&j,0,"research_state","HISTORICAL_ACCEPTANCE_EXPIRED")) :
            (j.token[0].count!=24 || !recovery_field(&j,0,"schema",RECOVERY_SCHEMA))) ||
       !recovery_field(&j,0,"recovery_class",RECOVERY_CLASS) ||
       !recovery_field(&j,0,"state","SPONSOR_APPROVED") || !recovery_field(&j,0,"attempt_identity",attempt) ||
       !recovery_string(&j,0,"sponsor_authorization_reference",reference,sizeof(reference)) ||
       !recovery_string(&j,0,"sponsor_authorization_path",sponsor_path,sizeof(sponsor_path)) ||
       !recovery_string(&j,0,"sponsor_authorization_sha256",sponsor_hash,sizeof(sponsor_hash)) || !valid_token(sponsor_hash) ||
       !recovery_file_digest(sponsor_path,actual,0) || strcmp(actual,sponsor_hash) ||
       !recovery_field(&j,0,"predecessor_revision",a->historical?RECOVERY_HISTORY_PREDECESSOR:RECOVERY_PREDECESSOR) ||
       !recovery_field(&j,0,"successor_revision",target) ||
       !recovery_field(&j,0,"expected_successor_capability",recovery_capability(a)) ||
       !recovery_field(&j,0,"compatibility_relation_sha256",recovery_relation(a)) ||
       !recovery_field(&j,0,"diagnosis_sha256",recovery_diagnosis(a)) ||
       !recovery_field(&j,0,"window_start",RECOVERY_WINDOW_START) || !recovery_field(&j,0,"window_end",RECOVERY_WINDOW_END) ||
       recovery_integer(&j,0,"predecessor_pid")!=pid ||
       !recovery_string(&j,0,"predecessor_maintenance_identity",a->maintenance,sizeof(a->maintenance)) || !valid_token(a->maintenance) ||
       !recovery_string(&j,0,"private_control_sha256",a->control_digest,sizeof(a->control_digest)) || !valid_token(a->control_digest) ||
       !recovery_file_digest(control,actual,1) || strcmp(actual,a->control_digest) ||
       !recovery_string(&j,0,"installed_package_identity",a->package,sizeof(a->package)) || !valid_token(a->package) ||
       !recovery_string(&j,0,"rollback_bundle",a->rollback,sizeof(a->rollback)) ||
       !recovery_separate_bundle(a->rollback,canonical_bundle) ||
       !recovery_string(&j,0,"rollback_package_identity",a->rollback_identity,sizeof(a->rollback_identity)) || !valid_token(a->rollback_identity) ||
       !recovery_string(&j,0,"relation_path",a->relation,sizeof(a->relation)) ||
       !recovery_file_digest(a->relation,actual,0) || strcmp(actual,recovery_relation(a)) ||
       !recovery_string(&j,0,"diagnosis_path",a->diagnosis,sizeof(a->diagnosis)) ||
       !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,recovery_diagnosis(a)) ||
       !recovery_file_digest(a->file,a->digest,1))return 0;
    unsigned char parsed_digest[CC_SHA256_DIGEST_LENGTH]; char parsed_hex[65];
    CC_SHA256(raw,(CC_LONG)strlen(raw),parsed_digest);
    for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)snprintf(parsed_hex+2*i,3,"%02x",parsed_digest[i]);
    if(strcmp(parsed_hex,a->digest))return 0;
    a->valid_from=recovery_integer(&j,0,"valid_from_us");a->valid_until=recovery_integer(&j,0,"valid_until_us");
    if(a->valid_from<0 || a->valid_until<=a->valid_from || !recovery_time_valid(a,now))return 0;
    a->pid=pid;strcpy(a->predecessor,a->historical?RECOVERY_HISTORY_PREDECESSOR:RECOVERY_PREDECESSOR);strcpy(a->successor,target);
    strcpy(a->sponsor,sponsor_path);strcpy(a->sponsor_digest,sponsor_hash);strcpy(a->control,control);return 1;
}
static const char *recovery_body(const char *response) {
    const char *p=strstr(response,"\r\n\r\n");return p?p+4:response;
}
static int recovery_maintenance_matches(const RecoveryJson *j,int object,
                                        const char *generation,int ready) {
    return recovery_field(j,object,"protocol","KRONOS_MAINTENANCE_HANDOFF_V1") &&
        recovery_field(j,object,"generation",generation) &&
        recovery_field(j,object,"state",ready?"INACTIVE":"FAILED_ACTIVE") &&
        recovery_field(j,object,"active",ready?"false":"true") &&
        recovery_field(j,object,"startup",ready?"READY":"BLOCKED") &&
        recovery_field(j,object,"failure",ready?"null":"ACCEPTANCE_RESTORATION_NOT_ESTABLISHED");
}
static int recovery_incident_maintenance(const RecoveryAuthorization *a,const RecoveryJson *j,int object) {
    if(!a->swing_incident)return recovery_maintenance_matches(j,object,a->maintenance,0);
    return recovery_field(j,object,"protocol","KRONOS_MAINTENANCE_HANDOFF_V1") &&
        recovery_field(j,object,"generation",RECOVERY_SWING_GENERATION) &&
        recovery_field(j,object,"state","FAILED_ACTIVE") && recovery_field(j,object,"active","true") &&
        recovery_field(j,object,"startup","BLOCKED") &&
        recovery_field(j,object,"failure","SWING_RESTORATION_NOT_ESTABLISHED");
}
static int recovery_worker_drainable(const RecoveryJson *j,int object,int owners,const char *kind) {
    long long workers=recovery_integer(j,object,"owned_workers"),queued=recovery_integer(j,object,"queued_items");
    if(workers<0 || queued<0 || !recovery_field(j,object,"continuity","COMPLETE") ||
       !recovery_field(j,object,"failure","null"))return 0;
    if(recovery_field(j,object,"state","IDLE"))return workers==0 && queued==0;
    /* The existing coordinator retains one owner ticket throughout each
     * worker's queue, callbacks and final writes. Zero is required by the
     * signed handoff, not by this pre-claim DRAINABLE check (ADR-0059). */
    return (recovery_field(j,object,"state","RUNNING") || recovery_field(j,object,"state","CANCELLATION_REQUESTED")) &&
        workers>0 && recovery_integer(j,object,"generation")>0 && recovery_integer(j,owners,kind)>=workers;
}
static int recovery_runtime_matches(const RecoveryAuthorization *a,const char *runtime,const char *status,const char *intraday) {
    RecoveryJson j,s,d;
    if(!recovery_json_document(&j,recovery_body(runtime)) || !recovery_json_document(&s,recovery_body(status)) ||
       !recovery_json_document(&d,recovery_body(intraday)))return 0;
    int process=recovery_json_get(&j,0,"process"),m=recovery_json_get(&j,0,"maintenance"),
        drain=recovery_json_get(&j,0,"maintenance_drain"),provider=recovery_json_get(&j,0,"provider_runtime"),
        monitor=recovery_json_get(&j,0,"monitoring"),shadow=recovery_json_get(&d,0,"live_shadow");
    if(!recovery_field(&j,0,"schema","KRONOS-RUNTIME-STATE/1.0.0") || recovery_integer(&j,process,"pid")!=a->pid ||
       !recovery_field(&j,process,"revision",a->predecessor) || !recovery_field(&j,process,"source_state","CLEAN_COMMIT") ||
       !recovery_incident_maintenance(a,&j,m) ||
       !recovery_incident_maintenance(a,&s,recovery_json_get(&s,0,"maintenance")) ||
       !recovery_field(&s,0,"service","KRONOS_BROWSER_V1") ||
       !recovery_field(&j,drain,"state","OPEN") || !recovery_field(&j,drain,"generation","null") || !recovery_field(&j,drain,"failure","null") ||
       !recovery_field(&j,0,"maintenance_claim","DRAINABLE") || !recovery_field(&s,0,"runtime_ready","false") ||
       !recovery_field(&s,0,"provider","DISCONNECTED") ||
       !recovery_field(&j,0,"rest_authentication","DISCONNECTED") || !recovery_field(&j,0,"rest_capability","ABSENT") ||
       !recovery_field(&j,0,"connection_attempt","null") ||
       !recovery_field(&j,provider,"cleanup_state","COMPLETE") || recovery_integer(&j,provider,"owned_work_count")!=0 ||
       recovery_integer(&j,provider,"retained_lease_count")!=0 || recovery_integer(&j,provider,"unresolved_cleanup_count")!=0 ||
       !recovery_field(&d,0,"active_operation_identity","null") || !recovery_field(&d,0,"current_failure","null") ||
       !recovery_field(&d,shadow,"failure",a->swing_incident?"null":(a->historical?"SHADOW_RESTORATION_WINDOW_NOT_ACTIVE":"SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE")) ||
       !recovery_field(&d,shadow,"runtime_accepted","false") || !recovery_field(&d,shadow,"epoch_failure","null") ||
       !recovery_field(&d,shadow,"publication_hook_failure","null"))return 0;
    int owners=recovery_json_get(&j,drain,"owners");if(owners<0 || j.token[owners].kind!='{')return 0;
    static const char *allowed[]={"SERVER_PULSE","HOUSEKEEPING","WO11","WO17","MONITORING_CALLBACK","NOTIFICATION","REMINDER","PROGRESSION","WO08_SHADOW"};
    for(int k=owners+1;k<j.token[owners].next;k=j.token[j.token[k].next].next){int known=0;
        for(size_t n=0;n<sizeof(allowed)/sizeof(allowed[0]);n++)if(recovery_json_equal(&j,k,allowed[n]))known=1;
        char name[64];int len=j.token[k].end-j.token[k].start;if(len<1 || len>=64)return 0;
        memcpy(name,j.text+j.token[k].start,(size_t)len);name[len]=0;
        if(!known || recovery_integer(&j,owners,name)<1)return 0;}
    for(int n=0;n<2;n++){int obj=recovery_json_get(&j,0,n?"intraday_wo17_work":"intraday_wo11_work");
        if(!recovery_worker_drainable(&j,obj,owners,n?"WO17":"WO11"))return 0;}
    for(int n=0;n<2;n++){int obj=recovery_json_get(&j,0,n?"analysis_execution":"analysis_work");
        if(!recovery_field(&j,obj,"state","IDLE") || recovery_integer(&j,obj,n?"owned_workers":"owned_work_count")!=0 ||
           recovery_integer(&j,obj,"queued_jobs")!=0)return 0;
        if(n && (!recovery_field(&j,obj,"cleanup_state","COMPLETE") || !recovery_field(&j,obj,"failure","null") ||
                  !recovery_field(&j,obj,"pid","null")))return 0;}
    static const char *zero[]={"session_count","active_session_count","owner_count","subscription_count"};
    for(size_t n=0;n<sizeof(zero)/sizeof(zero[0]);n++)if(recovery_integer(&j,monitor,zero[n])!=0)return 0;
    if(!recovery_field(&j,recovery_json_get(&j,monitor,"transport_cleanup"),"state","COMPLETE"))return 0;
    int house=recovery_json_get(&j,0,"housekeeping"),bulk=recovery_json_get(&j,0,"swing_bulk_import");
    long long house_workers=recovery_integer(&j,house,"owned_workers");
    int house_idle=recovery_field(&j,house,"lifecycle_state","IDLE") && house_workers==0 && recovery_field(&j,house,"pass_active","false");
    int house_counted=(recovery_field(&j,house,"lifecycle_state","RUNNING") || recovery_field(&j,house,"lifecycle_state","SCHEDULED")) &&
        house_workers>0 && recovery_integer(&j,house,"worker_generation")>0 &&
        recovery_integer(&j,owners,"HOUSEKEEPING")>=house_workers &&
        (recovery_field(&j,house,"pass_active","false") || recovery_field(&j,house,"pass_active","true"));
    return (house_idle || house_counted) && recovery_field(&j,house,"last_failure","null") &&
        recovery_field(&j,house,"shutdown_requested","false") && recovery_field(&j,bulk,"state","IDLE") &&
        recovery_field(&j,bulk,"batch_active","false");
}
static int recovery_run_helper(const char *repository,const char *executable,char *const arguments[],
                               const char *input,char *output,size_t capacity,int expected_exit);
static int recovery_swing_verify(const RecoveryAuthorization *a,const char *repository,const char *python,
                                 const char *phase,const char *documents,const char *generation,pid_t pid) {
    char output[100],process[32],maintenance[PATH_MAX],evidence[PATH_MAX];
    const char *home=getenv("HOME");if(!home)return 0;
    if(snprintf(maintenance,sizeof(maintenance),"%s/Library/Application Support/KRONOS/runtime/maintenance",home)>=(int)sizeof(maintenance) ||
       snprintf(evidence,sizeof(evidence),"%s/Library/Application Support/KRONOS/evidence",home)>=(int)sizeof(evidence))return 0;
    snprintf(process,sizeof(process),"%ld",(long)pid);
    char *arguments[]={(char*)python,"-B","tools/failed_active_successor.py","--incident-phase",(char*)phase,
        "--authorization",(char*)a->file,"--authorization-sha256",(char*)a->digest,
        "--revision",(char*)a->successor,"--generation",(char*)generation,"--pid",process,
        "--maintenance-root",maintenance,"--evidence-root",evidence,NULL};
    return recovery_run_helper(repository,python,arguments,documents,output,sizeof(output),0) &&
        !strcmp(output,"KRONOS_IWO07R3_RECOVERY_V1 VALID\n");
}
static int recovery_package_identity(const char *repository,const char *python,const char *bundle,char out[65]) {
    char raw[67];
    char *arguments[]={(char*)python,"-B","-c","import sys; from tools.macos.package_launcher import verify; print(verify(sys.argv[1]))",(char*)bundle,NULL};
    if(!recovery_run_helper(repository,python,arguments,NULL,raw,sizeof(raw),0) || strlen(raw)!=65 || raw[64]!='\n')return 0;
    memcpy(out,raw,64);out[64]=0;return valid_token(out);
}
static int recovery_listener_record(const char *raw,pid_t pid) {
    /* lsof emits one process record and one mandatory file-descriptor record. */
    char prefix[48];snprintf(prefix,sizeof(prefix),"p%ld\nf",(long)pid);
    size_t n=strlen(prefix);if(strncmp(raw,prefix,n))return 0;
    const char *p=raw+n,*start=p;
    while(*p>='0' && *p<='9')p++;
    return p!=start && !strcmp(p,"\nn127.0.0.1:8947\n");
}
static int recovery_listener_scan(pid_t pid,int absent) {
    char raw[256];char *arguments[]={"lsof","-nP","-Fpfn","-iTCP:8947","-sTCP:LISTEN",NULL};
    return recovery_run_helper(NULL,"/usr/sbin/lsof",arguments,NULL,raw,sizeof(raw),absent?1:0) &&
        (absent ? raw[0]==0 : recovery_listener_record(raw,pid));
}
static int recovery_listener_owner(pid_t pid) { return recovery_listener_scan(pid,0); }
static int recovery_attempt_record(const RecoveryAuthorization *a,const char *generation,
                                   long long now,char *record,size_t capacity) {
    return snprintf(record,capacity,"{\"schema\":\"KRONOS-FAILED-ACTIVE-RECOVERY-ATTEMPT/1.0.0\",\"attempt\":\"%s\",\"authorization_sha256\":\"%s\",\"generation\":\"%s\",\"predecessor_pid\":%ld,\"predecessor_revision\":\"%s\",\"successor_revision\":\"%s\",\"reserved_at_us\":%lld}\n",a->attempt,a->digest,generation,(long)a->pid,a->predecessor,a->successor,now);
}
static int recovery_attempt_matches(const RecoveryAuthorization *a,const char *generation) {
    char path[PATH_MAX],record[1024],retained[1024];
    int n=recovery_attempt_record(a,generation,a->reserved_at,record,sizeof(record));
    return valid_token(generation) && a->reserved_at>=a->valid_from && a->reserved_at<a->valid_until &&
        n>0 && n<(int)sizeof(record) &&
        snprintf(path,sizeof(path),"%s/%s.attempt.json",a->root,a->attempt)<(int)sizeof(path) &&
        recovery_read_file(path,retained,sizeof(retained),1) && !strcmp(record,retained);
}
static int recovery_reserve(RecoveryAuthorization *a,const char *generation,long long now) {
    if(!valid_token(generation) || !recovery_time_valid(a,now) || !recovery_safe_path(a->root,1,1))return 0;
    char actual[65],path[PATH_MAX],record[1024];
    if(!recovery_file_digest(a->file,actual,1) || strcmp(actual,a->digest) ||
       snprintf(path,sizeof(path),"%s/%s.attempt.json",a->root,a->attempt)>=(int)sizeof(path))return 0;
    int n=recovery_attempt_record(a,generation,now,record,sizeof(record));
    if(n<1 || n>=(int)sizeof(record))return 0;
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);if(fd<0)return 0;
    size_t used=0;int ok=1;while(used<(size_t)n){ssize_t written=write(fd,record+used,(size_t)n-used);
        if(written<0&&errno==EINTR)continue;if(written<=0){ok=0;break;}used+=(size_t)written;}
    if(fsync(fd)!=0)ok=0;if(close(fd)!=0)ok=0;
    int directory=open(a->root,O_RDONLY|O_NOFOLLOW);if(directory<0)return 0;
    if(fsync(directory)!=0)ok=0;close(directory);
    /* Never remove or reuse a partial reservation, even when sync/readback failed. */
    a->reserved_at=now;
    return ok && recovery_attempt_matches(a,generation);
}
static int recovery_bindings_match(const RecoveryAuthorization *a,const char *repository,
                                  const char *python,const char *control_proof) {
    long long now=recovery_now_us();char actual[65];
    if(!recovery_time_valid(a,now) ||
       !recovery_file_digest(a->file,actual,1) || strcmp(actual,a->digest) ||
       !recovery_file_digest(a->sponsor,actual,0) || strcmp(actual,a->sponsor_digest) ||
       !recovery_file_digest(a->relation,actual,0) || strcmp(actual,recovery_relation(a)) ||
       !recovery_file_digest(a->diagnosis,actual,0) || strcmp(actual,recovery_diagnosis(a)) ||
       !recovery_separate_bundle(a->rollback,canonical_bundle) ||
       !recovery_package_identity(repository,python,canonical_bundle,actual) || strcmp(actual,a->package) ||
       !recovery_package_identity(repository,python,a->rollback,actual) || strcmp(actual,a->rollback_identity) ||
       !qualify_source(repository,python) || !repository_revision_matches(repository,a->successor))return 0;
    if(control_proof){
        pid_t pid=0;char proof[65]={0};
        int ok=recovery_file_digest(a->control,actual,1) && !strcmp(actual,a->control_digest) &&
            recovery_control_record(a->control,&pid,proof) && pid==a->pid && !strcmp(proof,control_proof) &&
            recovery_file_digest(a->control,actual,1) && !strcmp(actual,a->control_digest);
        memset(proof,0,sizeof(proof));if(!ok)return 0;
    }
    if(a->swing_incident && ((!recovery_swing_verify(a,repository,python,"retired",NULL,a->maintenance,a->pid)) ||
        (control_proof && !recovery_swing_process_start(a->pid))))return 0;
    now=recovery_now_us();
    return recovery_time_valid(a,now);
}
static int recovery_assess(const RecoveryAuthorization *a,const char *repository,const char *python) {
    char runtime[BACKEND_STATUS_RESPONSE_BYTES],status[BACKEND_STATUS_RESPONSE_BYTES],intraday[BACKEND_STATUS_RESPONSE_BYTES];
    if(!(read_backend_route("/runtime/status",runtime) && read_backend_route("/status",status) &&
        read_backend_route("/control/intraday-discovery/v2/status",intraday) &&
        recovery_runtime_matches(a,runtime,status,intraday) && recovery_listener_owner(a->pid)))return 0;
    if(!a->swing_incident)return 1;
    char input[BACKEND_STATUS_RESPONSE_BYTES*3];
    return recovery_swing_process_start(a->pid) &&
        snprintf(input,sizeof(input),"[%s,%s,%s]",recovery_body(runtime),recovery_body(status),recovery_body(intraday))<(int)sizeof(input) &&
        recovery_swing_verify(a,repository,python,"preflight",input,a->maintenance,a->pid);
}

/* Helpers have no runtime authority; they only validate existing durable bytes
 * or documents fetched by this launcher. All paths are explicit arguments. */
static int recovery_run_helper(const char *repository,const char *executable,char *const arguments[],
                               const char *input,char *output,size_t capacity,int expected_exit) {
    long long saved=validation_deadline_ns;
    if(recovery_io_deadline) {
        long long deadline=(long long)recovery_io_deadline->tv_sec*1000000000LL+recovery_io_deadline->tv_nsec;
        if(!saved || deadline<saved)validation_deadline_ns=deadline;
    }
    int result=bounded_validation_cli(repository,executable,arguments,input,output,capacity,expected_exit,
                                     "RETAINED_RECOVERY_VALIDATOR",20);
    validation_deadline_ns=saved;return result;
}

static int recovery_continuity(const char *repository,const char *python,const char *home,const char *generation) {
    char evidence[PATH_MAX],output[160],path[PATH_MAX],raw[8192],state[32],digest[65],count[32];
    if(snprintf(evidence,sizeof(evidence),"%s/Library/Application Support/KRONOS/evidence",home)>=(int)sizeof(evidence))return 0;
    char *arguments[]={(char*)python,"-B","tools/failed_active_continuity.py","--evidence-root",evidence,
        NULL,NULL,NULL,NULL,NULL,NULL,NULL};
    if(generation){
        RecoveryJson j;
        if(!valid_token(generation) || snprintf(path,sizeof(path),"%s/Library/Application Support/KRONOS/runtime/maintenance/%s.json",home,generation)>=(int)sizeof(path) ||
           !recovery_read_file(path,raw,sizeof(raw),1) || !recovery_json_document(&j,raw))return 0;
        int record=recovery_json_get(&j,0,"record"),drain=recovery_json_get(&j,record,"drain"),
            checkpoint=recovery_json_get(&j,drain,"notification_checkpoint");
        long long pending=recovery_integer(&j,checkpoint,"pending_count");
        if(!recovery_field(&j,record,"generation",generation) || pending<0 ||
           !recovery_string(&j,checkpoint,"state",state,sizeof(state)) ||
           !recovery_string(&j,checkpoint,"sha256",digest,sizeof(digest)) || !valid_token(digest))return 0;
        snprintf(count,sizeof(count),"%lld",pending);
        arguments[5]="--checkpoint-state";arguments[6]=state;
        arguments[7]="--checkpoint-count";arguments[8]=count;
        arguments[9]="--checkpoint-sha256";arguments[10]=digest;
    }
    if(!recovery_run_helper(repository,python,arguments,NULL,output,sizeof(output),0))return 0;
    const char *prefix="KRONOS_CONTINUITY_V1 VALID ";size_t n=strlen(prefix);
    if(strncmp(output,prefix,n) || strlen(output)!=n+65 || output[n+64]!='\n')return 0;
    output[n+64]=0;return valid_token(output+n);
}
typedef struct RecoverySuccessorContext {
    const RecoveryAuthorization *authority;
    const char *repository,*python,*generation,*home;
    pid_t child;
    struct timespec deadline;
} RecoverySuccessorContext;
static RecoverySuccessorContext recovery_successor={0};

static int recovery_successor_ready(void) {
    const RecoveryAuthorization *a=recovery_successor.authority;
    char runtime[BACKEND_STATUS_RESPONSE_BYTES],status[BACKEND_STATUS_RESPONSE_BYTES],intraday[BACKEND_STATUS_RESPONSE_BYTES];
    pid_t controlled_pid=0;char proof[65]={0};
    if(!a || !recovery_control_record(a->control,&controlled_pid,proof))return 0;
    memset(proof,0,sizeof(proof));
    if(controlled_pid!=recovery_successor.child || !recovery_listener_owner(controlled_pid) ||
       !read_backend_route("/runtime/status",runtime) || !read_backend_route("/status",status) ||
       !read_backend_route("/control/intraday-discovery/v2/status",intraday))return 0;
    char input[BACKEND_STATUS_RESPONSE_BYTES*3],output[100],pid[32],parent[32],from[32],until[32],maintenance[PATH_MAX],evidence[PATH_MAX];
    if(snprintf(input,sizeof(input),"[%s,%s,%s]",recovery_body(runtime),recovery_body(status),recovery_body(intraday))>=(int)sizeof(input) ||
       snprintf(maintenance,sizeof(maintenance),"%s/Library/Application Support/KRONOS/runtime/maintenance",recovery_successor.home)>=(int)sizeof(maintenance) ||
       snprintf(evidence,sizeof(evidence),"%s/Library/Application Support/KRONOS/evidence",recovery_successor.home)>=(int)sizeof(evidence))return 0;
    snprintf(pid,sizeof(pid),"%ld",(long)controlled_pid);snprintf(parent,sizeof(parent),"%ld",(long)a->pid);
    snprintf(from,sizeof(from),"%lld",a->valid_from);snprintf(until,sizeof(until),"%lld",a->valid_until);
    char *arguments[]={(char*)recovery_successor.python,"-B","tools/failed_active_successor.py",
        "--relation",(char*)a->relation,"--relation-sha256",(char*)recovery_relation(a),
        "--capability",(char*)recovery_capability(a),"--pid",pid,"--parent-pid",parent,
        "--revision",(char*)a->successor,"--generation",(char*)recovery_successor.generation,
        "--maintenance-root",maintenance,"--evidence-root",evidence,"--valid-from-us",from,"--valid-until-us",until,
        "--research-state",a->historical?"HISTORICAL_ACCEPTANCE_EXPIRED":"ACTIVE",NULL};
    int verified=a->swing_incident ? recovery_swing_verify(a,recovery_successor.repository,
        recovery_successor.python,"successor",input,recovery_successor.generation,controlled_pid) :
        (recovery_run_helper(recovery_successor.repository,recovery_successor.python,arguments,input,output,sizeof(output),0) &&
        !strcmp(output,"KRONOS_RECOVERY_SUCCESSOR_V1 VALID\n"));
    int valid=verified &&
        recovery_attempt_matches(a,recovery_successor.generation) &&
        recovery_listener_owner(controlled_pid) &&
        recovery_time_valid(a,recovery_now_us());
    struct timespec now;
    return valid && monotonic_now(&now)==0 && !time_reached(&now,&recovery_successor.deadline);
}
static int native_recovery_ready(void) {
    return recovery_successor_ready() && native_ready();
}

static BackendStartResult start_backend(
    const char *repository,
    const char *python,
    const char *browser_entry,
    const char *python_path,
    pid_t previous_pid,
    const char *previous_token,
    const char *generation,
    const char *previous_revision
) {
    if (!admission_still_bound() || !validation_permitted()) return BACKEND_START_INTERNAL_FAILURE;
    long long before_fork=validation_now_ns();if(!before_fork)return BACKEND_START_INTERNAL_FAILURE;
    long long original_deadline=validation_current_deadline();
    backend_ready_deadline_ns=before_fork+(long long)BACKEND_START_READY_TIMEOUT_SECONDS*1000000000LL;
    if(!strcmp(native_startup.mode,"ORDINARY") && original_deadline && original_deadline<backend_ready_deadline_ns)
        backend_ready_deadline_ns=original_deadline;
    struct timespec backend_io_deadline={
        .tv_sec=(time_t)(backend_ready_deadline_ns/1000000000LL),
        .tv_nsec=(long)(backend_ready_deadline_ns%1000000000LL)};
    validation_phase="BACKEND_STARTUP";
    validation_deadline_ns=backend_ready_deadline_ns;
    if(native_startup.active &&
       ((!native_startup.restoration && !native_advance("CHILD_START_RESERVED","{}")) ||
        !native_child_environment()))return BACKEND_START_INTERNAL_FAILURE;
    int dispatch[2]={-1,-1};
    if(native_startup.active && pipe(dispatch)!=0)return BACKEND_START_INTERNAL_FAILURE;
    pid_t child = fork();
    if (child < 0) {
        if(dispatch[0]>=0){close(dispatch[0]);close(dispatch[1]);}
        return BACKEND_START_INTERNAL_FAILURE; /* Sole-fork allowance stays spent. */
    }
    if (child == 0) {
        if(native_startup.active) {
            close(dispatch[1]);char accepted=0;
            struct pollfd ready={dispatch[0],POLLIN|POLLHUP,0};
            long long remaining=backend_ready_deadline_ns-validation_now_ns();
            if(remaining<=0 || poll(&ready,1,(int)(remaining/1000000LL))<=0 ||
               read(dispatch[0],&accepted,1)!=1 || accepted!='D')_exit(1);
            close(dispatch[0]);
            if(native_startup.restoration) {
                char birth[65];if(!native_process_birth(getpid(),birth) ||
                    setenv("KRONOS_RESTORATION_CHILD_KERNEL_BIRTH",birth,1)!=0)_exit(1);
            }
        }
        /* Only this child inherits the original held open-file description. */
        if (!admission_still_bound()) _exit(1);
        if (dup2(admission_descriptor, ADMISSION_BACKEND_DESCRIPTOR)<0) _exit(1);
        if (admission_descriptor!=ADMISSION_BACKEND_DESCRIPTOR) close(admission_descriptor);
        admission_descriptor=ADMISSION_BACKEND_DESCRIPTOR;
        if (fcntl(admission_descriptor,F_SETFD,FD_CLOEXEC)<0) _exit(1);
        if (setsid() < 0) _exit(1);
        /* Keep the canonical parent alive until the backend qualifies itself. */

        int devnull = open("/dev/null", O_RDWR);
        if (devnull >= 0) {
            (void)dup2(devnull, STDIN_FILENO);
            (void)dup2(devnull, STDOUT_FILENO);
            /* Preserve controlled-attempt stderr for bounded structured outcomes. */
            if (devnull > STDERR_FILENO) (void)close(devnull);
        }
        if (chdir(repository) != 0 || setenv("PYTHONPATH", python_path, 1) != 0) {
            _exit(1);
        }
        if (previous_pid > 0) {
            char parent[32];
            (void)snprintf(parent, sizeof(parent), "%ld", (long)previous_pid);
            if (setenv("KRONOS_MAINTENANCE_GENERATION", generation, 1) != 0 ||
                setenv("KRONOS_MAINTENANCE_PARENT", parent, 1) != 0 ||
                setenv("KRONOS_MAINTENANCE_PROOF", previous_token, 1) != 0) _exit(1);
            if (previous_revision != NULL && previous_revision[0] != '\0') {
                if (setenv("KRONOS_MAINTENANCE_PROTOCOL", "V2", 1) != 0 ||
                    setenv("KRONOS_MAINTENANCE_REVISION", previous_revision, 1) != 0) _exit(1);
            } else if (unsetenv("KRONOS_MAINTENANCE_PROTOCOL") != 0 ||
                       unsetenv("KRONOS_MAINTENANCE_REVISION") != 0) _exit(1);
        } else {
            (void)unsetenv("KRONOS_MAINTENANCE_GENERATION");
            (void)unsetenv("KRONOS_MAINTENANCE_PARENT");
            (void)unsetenv("KRONOS_MAINTENANCE_PROOF");
            (void)unsetenv("KRONOS_MAINTENANCE_PROTOCOL");
            (void)unsetenv("KRONOS_MAINTENANCE_REVISION");
        }
        const char *launch_mode = getenv("KRONOS_LAUNCH_MODE");
        if (
            launch_mode != NULL && (strcmp(launch_mode, "GOVERNED_REPLACEMENT") == 0 || strcmp(launch_mode, RECOVERY_CLASS) == 0) &&
            (unsetenv("KRONOS_LAUNCH_MODE") != 0 ||
             unsetenv("KRONOS_REPLACEMENT_REVISION") != 0 || unsetenv("KRONOS_RECOVERY_ATTEMPT") != 0)
        ) _exit(1);
        char deadline_text[32];
        if(snprintf(deadline_text,sizeof(deadline_text),"%lld",backend_ready_deadline_ns)>=(int)sizeof(deadline_text) ||
           setenv("KRONOS_VALIDATION_CLOCK","CLOCK_MONOTONIC",1)!=0 ||
           setenv("KRONOS_VALIDATION_DEADLINE_NS",deadline_text,1)!=0 || !operation_boot_bound() ||
           setenv("KRONOS_VALIDATION_BOOT_SESSION",operation_boot_identity,1)!=0)_exit(1);
        if (fcntl(admission_descriptor,F_SETFD,0)<0) _exit(1);
        execl(python, python, "-B", browser_entry, "--no-browser", (char *)NULL);
        _exit(1);
    }
    admission_child=child;
    if(native_startup.active) {
        close(dispatch[0]);
        if(!native_identify_child(child)) {close(dispatch[1]);return BACKEND_START_INTERNAL_FAILURE;}
        /* Readback happened before the only child is allowed to exec. */
        if(write(dispatch[1],"D",1)!=1){close(dispatch[1]);return BACKEND_START_INTERNAL_FAILURE;}
        close(dispatch[1]);
    }
    BackendStartMonitor monitor=production_backend_start_monitor;
    if(native_startup.active)monitor.ready=native_ready;
    recovery_io_deadline=&backend_io_deadline;
    if(recovery_successor.authority){
        recovery_successor.child=child;monitor.ready=native_startup.active?native_recovery_ready:recovery_successor_ready;
        recovery_successor.deadline.tv_sec=(time_t)(backend_ready_deadline_ns/1000000000LL);
        recovery_successor.deadline.tv_nsec=(long)(backend_ready_deadline_ns%1000000000LL);
        recovery_io_deadline=&recovery_successor.deadline;
    }
    BackendStartResult result=monitor_backend_start(
        child,
        BACKEND_START_READY_TIMEOUT_SECONDS,
        &monitor
    );
    recovery_io_deadline=NULL;
    if(result==BACKEND_START_READY) admission_ready=1;
    return result;
}

/* Bounded inventory of the governed user's canonical entry processes. Unknown
 * argument observations deny; this is not a claim about arbitrary other users
 * or about a process executing modified/unapproved entry code. */
static int initialization_process_inventory(pid_t enrolled) {
    pid_t pids[16384];int found=0;
    int bytes=proc_listpids(PROC_UID_ONLY,getuid(),pids,sizeof(pids));
    if(bytes<=0 || bytes>=(int)sizeof(pids) || bytes%(int)sizeof(pid_t))return 0;
    for(int i=0;i<bytes/(int)sizeof(pid_t);i++) {
        pid_t pid=pids[i];if(pid<=1 || pid==getpid())continue;
        if(!validation_permitted())return 0;
        int mib[]={CTL_KERN,KERN_PROCARGS2,pid};char arguments[262144];size_t size=sizeof(arguments);
        if(sysctl(mib,3,arguments,&size,NULL,0)!=0 || size<=sizeof(int) || size>=sizeof(arguments))return 0;
        int relevant=0;size_t offset=sizeof(int);
        while(offset<size) {
            size_t n=strnlen(arguments+offset,size-offset);if(n==size-offset)return 0;
            const char *arg=arguments+offset;
            const char *suffix="/tools/kronos_browser.py";size_t width=strlen(suffix);
            if((n>=width && !strcmp(arg+n-width,suffix)) || !strcmp(arg,"tools.kronos_browser") ||
               !strcmp(arg,canonical_executable))relevant=1;
            offset+=n+1;
        }
        if(relevant){if(pid!=enrolled)return 0;found++;}
    }
    return enrolled>1 ? found==1 : found==0;
}
static int initialization_environment_reference(const char *prefix,char *out,size_t capacity) {
    char key[128];const char *values[4];const char *suffix[]={"PATH","BYTES","SHA256","ID"};
    for(int i=0;i<4;i++){snprintf(key,sizeof(key),"%s_%s",prefix,suffix[i]);values[i]=getenv(key);if(!values[i])return 0;}
    long maximum=!strcmp(prefix,"KRONOS_INITIALIZATION_PREDECESSOR")?8*1024*1024:65536;
    if(values[0][0]!='/' || !native_json_text(values[0]) || !*values[1] || strlen(values[1])>7 ||
       strspn(values[1],"0123456789")!=strlen(values[1]) || atol(values[1])<1 || atol(values[1])>maximum ||
       !valid_token(values[2]) || !native_identity(values[3]))return 0;
    int n=snprintf(out,capacity,"{\"bytes\":%ld,\"identity\":\"%s\",\"path\":\"%s\",\"sha256\":\"%s\"}",
        atol(values[1]),values[3],values[0],values[2]);return n>0 && (size_t)n<capacity;
}
static int initialization_eligibility(const char *control,pid_t predecessor,const char *birth) {
    if(!initialization_process_inventory(predecessor) || !validation_permitted())return 0;
    if(predecessor==0)return cold_start_has_no_control_or_live_handoff(control) && recovery_listener_scan(0,1);
    pid_t current=0;char token[65],observed[65];
    int ok=recovery_control_record(control,&current,token) && current==predecessor &&
        native_process_birth(current,observed) && !strcmp(observed,birth) && recovery_listener_owner(current);
    memset(token,0,sizeof(token));return ok && validation_permitted();
}
static int native_initialize(const char *repository,const char *python,const char *control) {
    if(!repository || !python || !control || strlen(repository)>=sizeof(native_startup.repository) ||
       strlen(python)>=sizeof(native_startup.python))return 1;
    const char *eligibility=getenv("KRONOS_INITIALIZATION_ELIGIBILITY");
    char order[PATH_MAX+400],predecessor_ref[PATH_MAX+400],observed[240],birth[65]={0},details[2*PATH_MAX+1400];
    pid_t predecessor=0;char token[65];
    const char *known[]={"KRONOS_INITIALIZATION_ELIGIBILITY=","KRONOS_INITIALIZATION_ORDER_PATH=",
        "KRONOS_INITIALIZATION_ORDER_BYTES=","KRONOS_INITIALIZATION_ORDER_SHA256=","KRONOS_INITIALIZATION_ORDER_ID=",
        "KRONOS_INITIALIZATION_PREDECESSOR_PATH=","KRONOS_INITIALIZATION_PREDECESSOR_BYTES=",
        "KRONOS_INITIALIZATION_PREDECESSOR_SHA256=","KRONOS_INITIALIZATION_PREDECESSOR_ID="};
    extern char **environ;
    for(char **e=environ;*e;e++)if(!strncmp(*e,"KRONOS_INITIALIZATION_",22)) {
        int recognized=0;for(size_t k=0;k<sizeof(known)/sizeof(known[0]);k++)
            if(!strncmp(*e,known[k],strlen(known[k])))recognized=1;
        if(!recognized)return 1;
    }
    if(!eligibility || (strcmp(eligibility,"COLD_ABSENT") && strcmp(eligibility,"EXISTING_RELEASE_B")) ||
       !initialization_environment_reference("KRONOS_INITIALIZATION_ORDER",order,sizeof(order)) ||
       !native_select_environment())return 1;
    if(!strcmp(eligibility,"EXISTING_RELEASE_B")) {
        if(!initialization_environment_reference("KRONOS_INITIALIZATION_PREDECESSOR",predecessor_ref,sizeof(predecessor_ref)) ||
           !recovery_control_record(control,&predecessor,token) || !native_process_birth(predecessor,birth))return 1;
        memset(token,0,sizeof(token));
        snprintf(observed,sizeof(observed),"{\"kernel_birth\":\"%s\",\"pid\":%ld}",birth,(long)predecessor);
    } else {
        extern char **environ;
        for(char **e=environ;*e;e++)if(!strncmp(*e,"KRONOS_INITIALIZATION_PREDECESSOR_",34))return 1;
        strcpy(predecessor_ref,"null");strcpy(observed,"null");
    }
    struct stat exists;
    if(fstatat(admission_descriptor,"failed-successor-restore-v1",&exists,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT ||
       !initialization_eligibility(control,predecessor,birth))return 1;
    strcpy(native_startup.repository,repository);strcpy(native_startup.python,python);
    strcpy(native_startup.mode,"ADMISSION_HEAD_INITIALIZATION");native_startup.parent=getpid();
    if(!native_process_birth(getpid(),native_startup.parent_birth))return 1;
    char id[80];unsigned char random[24];arc4random_buf(random,sizeof(random));strcpy(id,"initialization-");
    for(size_t i=0;i<sizeof(random);i++)snprintf(id+15+2*i,3,"%02x",random[i]);
    int n=snprintf(details,sizeof(details),"{\"eligibility\":\"%s\",\"observed_predecessor\":%s,\"operator_order\":%s,\"predecessor_evidence\":%s}",
        eligibility,observed,order,predecessor_ref);
    if(n<1 || (size_t)n>=sizeof(details) || !native_validation("initialization-prepare",id,details,1))return 1;
    RecoveryJson proposal,head,phase,attempt;
    char head_raw[NATIVE_DOCUMENT_BYTES],phase_raw[NATIVE_DOCUMENT_BYTES],attempt_raw[NATIVE_DOCUMENT_BYTES],digest[65],
        path[240],readback[NATIVE_DOCUMENT_BYTES];
    if(!recovery_json_document(&proposal,native_startup.last_result) ||
       !native_copy_json(&proposal,recovery_json_get(&proposal,0,"head"),head_raw,sizeof(head_raw)) ||
       !native_copy_json(&proposal,recovery_json_get(&proposal,0,"phase"),phase_raw,sizeof(phase_raw)) ||
       !native_copy_json(&proposal,recovery_json_get(&proposal,0,"attempt"),attempt_raw,sizeof(attempt_raw)) ||
       !recovery_json_document(&head,head_raw) || !recovery_json_document(&phase,phase_raw) ||
       !recovery_json_document(&attempt,attempt_raw) || !recovery_field(&attempt,0,"attempt_id",id) ||
       recovery_integer(&attempt,0,"deadline_ns")!=validation_current_deadline() ||
       !recovery_field(&phase,0,"identity",id) || !recovery_field(&phase,0,"phase","NATIVE_ACTIVATED") ||
       !recovery_field(&head,0,"active_reservation_id",id) || recovery_integer(&head,0,"sequence")!=1 ||
       !recovery_string(&head,0,"installation_identity",native_journal.installation,sizeof(native_journal.installation)))return 1;
    native_digest(phase_raw,strlen(phase_raw),digest);if(!recovery_field(&head,0,"active_reservation_sha256",digest))return 1;
    if(!initialization_eligibility(control,predecessor,birth) || !admission_still_bound() || !validation_permitted() ||
       fstatat(admission_descriptor,"failed-successor-restore-v1",&exists,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT ||
       mkdirat(admission_descriptor,"failed-successor-restore-v1",0700)!=0)return 1;
    native_journal.writer=getpid();
    native_journal.root=openat(admission_descriptor,"failed-successor-restore-v1",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(native_journal.root<0 || !native_root_bound() || fsync(admission_descriptor)!=0 || !validation_permitted() ||
       !native_exclusive("initialization-attempt.json",attempt_raw) || !native_exclusive("head-1.json",head_raw))return 1;
    snprintf(path,sizeof(path),"%s.json",id);
    if(!native_exclusive(path,phase_raw) || !native_exclusive("admission-head.json",head_raw) ||
       !native_validation("initialization-recheck",id,details,1) ||
       !native_read(native_journal.root,"initialization-attempt.json",readback,sizeof(readback)) || strcmp(readback,attempt_raw) ||
       !native_read(native_journal.root,path,readback,sizeof(readback)) || strcmp(readback,phase_raw) ||
       !native_read(native_journal.root,"head-1.json",readback,sizeof(readback)) || strcmp(readback,head_raw) ||
       !native_read(native_journal.root,"admission-head.json",readback,sizeof(readback)) || strcmp(readback,head_raw) ||
       !initialization_eligibility(control,predecessor,birth) || !native_root_bound() || !validation_permitted())return 1;
    /* No native_reload/admission success here, no final success receipt and no
     * ordinary fallback. Later invocations cannot reseed this root. */
    puts("PREPARED_PENDING_EXACT_ADMISSION_REVIEW");return 0;
}
static int initialization_return(int result) {
    if(native_journal.root>=0){if(close(native_journal.root)!=0)result=1;native_journal.root=-1;}
    if(validation_owned_child()>0)validation_cleanup_unresolved=1;
    /* Use the existing actual helper/child retention owner. A CLI-only route
     * must not turn helper exit 79 into process exit and kernel lock release. */
    finish_admission();
    return result;
}

/* Explicit setup never dispatches a child or infers admission. Exclusive
 * intents precede effects; incomplete/late artifacts are retained, not fixed.
 * The later separately pinned genesis decision must bind preparation inputs. */
static int setup_directory_bound(int directory,const char *name) {
    struct stat held,named;
    return validation_permitted() && admission_still_bound() &&
        fstat(directory,&held)==0 && S_ISDIR(held.st_mode) && held.st_uid==getuid() &&
        (held.st_mode&0777)==0700 &&
        fstatat(admission_descriptor,name,&named,AT_SYMLINK_NOFOLLOW)==0 &&
        held.st_dev==named.st_dev && held.st_ino==named.st_ino && S_ISDIR(named.st_mode);
}
static int setup_bound(int directory) {return setup_directory_bound(directory,"controlled-setup-v1");}
static int setup_write_exact(int directory,const char *root_name,const char *name,const char *raw) {
    if(!setup_directory_bound(directory,root_name) || !native_identity(name) || !raw || !*raw || strlen(raw)>=NATIVE_DOCUMENT_BYTES)return 0;
    int fd=openat(directory,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return 0;
    size_t used=0,size=strlen(raw);int ok=1;
    while(used<size) {
        if(!setup_directory_bound(directory,root_name)){ok=0;break;}
        ssize_t n=write(fd,raw+used,size-used);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=0;break;}used+=(size_t)n;
    }
    if(ok && fsync(fd)!=0)ok=0;if(close(fd)!=0)ok=0;
    if(ok && fsync(directory)!=0)ok=0;
    char observed[NATIVE_DOCUMENT_BYTES];
    return ok && native_read(directory,name,observed,sizeof(observed)) && !strcmp(raw,observed) && setup_directory_bound(directory,root_name);
}
static int setup_exclusive(int directory,const char *name,const char *raw) {
    return setup_write_exact(directory,"controlled-setup-v1",name,raw);
}
static int setup_absence(const char *control,int stale,pid_t expected) {
    if(!initialization_process_inventory(0) || !recovery_listener_scan(0,1) || !validation_permitted())return 0;
    if(!stale)return cold_start_has_no_control_or_live_handoff(control);
    pid_t pid=0;char token[65];int ok=recovery_control_record(control,&pid,token) && pid==expected;
    memset(token,0,sizeof(token));
    if(!ok || kill(pid,0)==0 || errno!=ESRCH)return 0;
    /* Any retained live handoff still fences preparation. */
    return no_live_handoff(control) && validation_permitted();
}
static int native_setup_activate(const char *repository,const char *python,const char *control) {
    if(!approved_persistent_binding || !initialization_policy() || !approved_ordinary_restart_policy ||
       !repository || !python || !control || strlen(repository)>=sizeof(native_startup.repository) ||
       strlen(python)>=sizeof(native_startup.python) || !setup_absence(control,0,0))return 1;
    extern char **environ;
    const char *allowed[]={"KRONOS_SETUP_OPERATION=","KRONOS_SETUP_ORDER_PATH=","KRONOS_SETUP_ORDER_BYTES=",
        "KRONOS_SETUP_ORDER_SHA256=","KRONOS_SETUP_ORDER_ID=","KRONOS_SETUP_INPUT_PATH=",
        "KRONOS_SETUP_INPUT_BYTES=","KRONOS_SETUP_INPUT_SHA256=","KRONOS_SETUP_INPUT_ID="};
    for(char **e=environ;*e;e++)if(!strncmp(*e,"KRONOS_SETUP_",13)) {
        int known=0;for(size_t i=0;i<sizeof(allowed)/sizeof(allowed[0]);i++)
            if(!strncmp(*e,allowed[i],strlen(allowed[i])))known=1;
        if(!known)return 1;
    }
    char order[PATH_MAX+400],input[PATH_MAX+400],details[2*PATH_MAX+1200],installation[65];RecoveryJson policy;
    if(!initialization_environment_reference("KRONOS_SETUP_ORDER",order,sizeof(order)) ||
       !initialization_environment_reference("KRONOS_SETUP_INPUT",input,sizeof(input)) || !native_select_environment() ||
       !recovery_json_document(&policy,approved_persistent_binding) ||
       !recovery_string(&policy,0,"installation_identity",installation,sizeof(installation)) || !valid_token(installation))return 1;
    strcpy(native_startup.repository,repository);strcpy(native_startup.python,python);
    strcpy(native_startup.mode,"CONTROLLED_INSTALLATION_SETUP");native_startup.parent=getpid();
    if(!native_process_birth(getpid(),native_startup.parent_birth) || !native_open_journal(installation) ||
       native_journal.sequence!=1 || strcmp(native_journal.state,"NATIVE_ACTIVATED"))return 1;
    int n=snprintf(details,sizeof(details),"{\"input\":%s,\"operation\":\"ACTIVATE_SELECTION\",\"operator_order\":%s}",input,order);
    if(n<1 || (size_t)n>=sizeof(details) || !native_validation("setup-prepare","setup-activation",details,1))return 1;
    RecoveryJson proposal,intent;char intent_raw[NATIVE_DOCUMENT_BYTES],selected_raw[NATIVE_DOCUMENT_BYTES],
        activation_raw[NATIVE_DOCUMENT_BYTES],record[NATIVE_DOCUMENT_BYTES],expected[65],observed[NATIVE_DOCUMENT_BYTES];
    if(!recovery_json_document(&proposal,native_startup.last_result) || !native_helper_agreement(&proposal) ||
       !recovery_field(&proposal,0,"disposition","PREPARED_ACTIVATION_UNPROVED") ||
       !native_copy_json(&proposal,recovery_json_get(&proposal,0,"intent"),intent_raw,sizeof(intent_raw)) ||
       !native_copy_json(&proposal,recovery_json_get(&proposal,0,"installed_selection"),selected_raw,sizeof(selected_raw)) ||
       !native_copy_json(&proposal,recovery_json_get(&proposal,0,"activation"),activation_raw,sizeof(activation_raw)) ||
       !native_copy_json(&proposal,recovery_json_get(&proposal,0,"record"),record,sizeof(record)) ||
       !recovery_string(&proposal,recovery_json_get(&proposal,0,"head"),"sha256",expected,sizeof(expected)) ||
       !recovery_json_document(&intent,intent_raw) || !recovery_field(&intent,0,"identity","setup-activation") ||
       !recovery_field(&intent,0,"original_outcome","UNPROVED") ||
       recovery_integer(&intent,recovery_json_get(&intent,0,"timing"),"deadline_ns")!=validation_current_deadline() ||
       !native_reload() || strcmp(expected,native_journal.head_digest) || !setup_absence(control,0,0) ||
       validation_owned_child()>0 || validation_has_unresolved())return 1;
    int directory=openat(admission_descriptor,"controlled-setup-v1",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(directory<0)return 1;
    int installed=-1,ok=setup_bound(directory) && setup_exclusive(directory,"activation.intent.json",intent_raw);
    if(ok)ok=mkdirat(admission_descriptor,"ordinary-start-v1",0700)==0 && fsync(admission_descriptor)==0;
    if(ok)installed=openat(admission_descriptor,"ordinary-start-v1",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(installed<0)ok=0;
    if(ok)ok=setup_write_exact(installed,"ordinary-start-v1","installed-selection.json",selected_raw) &&
        setup_write_exact(installed,"ordinary-start-v1","activation.json",activation_raw);
    if(installed>=0 && close(installed)!=0)ok=0;
    if(ok) {
        setup_activation_writer=getpid();setup_activation_deadline=validation_current_deadline();
        native_digest(intent_raw,strlen(intent_raw),setup_activation_intent_sha256);
        strcpy(setup_activation_parent_birth,native_startup.parent_birth);
        /* Last validation helper is fully terminal BEFORE any head commit.
         * Unknown verification leaves no activation phase and stays fenced
         * even after custodian death. There is no helper after final commit. */
        ok=native_validation("setup-verify-prepared","setup-activation",details,1);
        RecoveryJson verified;
        if(ok)ok=recovery_json_document(&verified,native_startup.last_result) && native_helper_agreement(&verified) &&
            recovery_field(&verified,0,"intent_sha256",setup_activation_intent_sha256) &&
            validation_owned_child()==0 && !validation_has_unresolved() && setup_absence(control,0,0) &&
            native_reload() && !strcmp(expected,native_journal.head_digest) &&
            native_commit("ORDINARY_ACTIVATED","setup-activation.ordinary-activated",NULL,record);
    }
    setup_activation_writer=0;setup_activation_deadline=0;memset(setup_activation_intent_sha256,0,sizeof(setup_activation_intent_sha256));
    memset(setup_activation_parent_birth,0,sizeof(setup_activation_parent_birth));
    if(ok)ok=setup_bound(directory) && native_read(directory,"activation.intent.json",observed,sizeof(observed)) &&
        !strcmp(observed,intent_raw) && native_reload() && !strcmp(native_journal.state,"ORDINARY_ACTIVATED") &&
        validation_owned_child()==0 && !validation_has_unresolved() && validation_permitted();
    if(close(directory)!=0)ok=0;
    if(!ok || !validation_permitted() || !admission_still_bound())return 1;
    puts("PREPARED_ACTIVATION_UNPROVED");return 0;
}
static int native_setup(const char *repository,const char *python,const char *control) {
    const char *operation=getenv("KRONOS_SETUP_OPERATION");
    if(operation && !strcmp(operation,"ACTIVATE_SELECTION"))return native_setup_activate(repository,python,control);
    int enrollment=operation && !strcmp(operation,"PLACE_ENROLLMENT");
    int stale=operation && !strcmp(operation,"PRESERVE_STALE_CONTROL");
    if((!enrollment && !stale) || !approved_persistent_binding || initialization_policy() ||
       approved_ordinary_restart_policy || !repository || !python || !control ||
       strlen(repository)>=sizeof(native_startup.repository) || strlen(python)>=sizeof(native_startup.python))return 1;
    extern char **environ;
    const char *allowed[]={"KRONOS_SETUP_OPERATION=","KRONOS_SETUP_ORDER_PATH=","KRONOS_SETUP_ORDER_BYTES=",
        "KRONOS_SETUP_ORDER_SHA256=","KRONOS_SETUP_ORDER_ID=","KRONOS_SETUP_INPUT_PATH=",
        "KRONOS_SETUP_INPUT_BYTES=","KRONOS_SETUP_INPUT_SHA256=","KRONOS_SETUP_INPUT_ID="};
    for(char **e=environ;*e;e++)if(!strncmp(*e,"KRONOS_SETUP_",13)) {
        int known=0;for(size_t i=0;i<sizeof(allowed)/sizeof(allowed[0]);i++)
            if(!strncmp(*e,allowed[i],strlen(allowed[i])))known=1;
        if(!known)return 1;
    }
    struct stat exists,original;
    if(fstatat(admission_descriptor,"failed-successor-restore-v1",&exists,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT)return 1;
    char order[PATH_MAX+400],input[PATH_MAX+400],details[2*PATH_MAX+1200],raw[NATIVE_DOCUMENT_BYTES],
        input_path[PATH_MAX],input_id[201],actual_ref[PATH_MAX+400],destination[PATH_MAX];
    if(!initialization_environment_reference("KRONOS_SETUP_ORDER",order,sizeof(order)) ||
       !initialization_environment_reference("KRONOS_SETUP_INPUT",input,sizeof(input)) || !native_select_environment())return 1;
    RecoveryJson ref;
    if(!recovery_json_document(&ref,input) || !recovery_string(&ref,0,"path",input_path,sizeof(input_path)) ||
       !recovery_string(&ref,0,"identity",input_id,sizeof(input_id)) ||
       !native_reference(input_path,input_id,actual_ref,sizeof(actual_ref)) || strcmp(input,actual_ref))return 1;
    char source_dir[PATH_MAX];strcpy(source_dir,input_path);char *source_name=strrchr(source_dir,'/');
    if(!source_name)return 1;*source_name++=0;
    int source=open(source_dir,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(source<0)return 1;
    int ok=native_read(source,source_name,raw,sizeof(raw)) &&
        fstatat(source,source_name,&original,AT_SYMLINK_NOFOLLOW)==0;
    if(close(source)!=0)ok=0;if(!ok)return 1;
    pid_t pid=0;char token[65];
    if(stale && (!recovery_control_record(control,&pid,token) || strcmp(input_path,control)))return 1;
    memset(token,0,sizeof(token));
    /* Enrollment may precede stale-control preservation. A selected stale
     * record is never consumed here; no service token is sent. */
    if(enrollment) {
        struct stat selected;
        if(!initialization_process_inventory(0) || !recovery_listener_scan(0,1) || !no_live_handoff(control))return 1;
        if(lstat(control,&selected)==0) {
            if(!recovery_control_record(control,&pid,token)){memset(token,0,sizeof(token));return 1;}
            memset(token,0,sizeof(token));
            if(kill(pid,0)==0 || errno!=ESRCH)return 1;
        } else if(errno!=ENOENT)return 1;
    } else if(!setup_absence(control,1,pid))return 1;
    strcpy(native_startup.repository,repository);strcpy(native_startup.python,python);
    strcpy(native_startup.mode,"CONTROLLED_INSTALLATION_SETUP");native_startup.parent=getpid();
    if(!native_process_birth(getpid(),native_startup.parent_birth))return 1;
    const char *identity=enrollment?"setup-enrollment":"setup-stale-control";
    int n=snprintf(details,sizeof(details),"{\"input\":%s,\"operation\":\"%s\",\"operator_order\":%s}",input,operation,order);
    if(n<1 || (size_t)n>=sizeof(details) || !native_validation("setup-prepare",identity,details,1))return 1;
    RecoveryJson proposal,attempt;char attempt_raw[NATIVE_DOCUMENT_BYTES];
    if(!recovery_json_document(&proposal,native_startup.last_result) ||
       !native_helper_agreement(&proposal) ||
       !recovery_string(&proposal,0,"destination",destination,sizeof(destination)) ||
       !native_copy_json(&proposal,recovery_json_get(&proposal,0,"attempt"),attempt_raw,sizeof(attempt_raw)) ||
       !recovery_json_document(&attempt,attempt_raw) || !recovery_field(&attempt,0,"identity",identity) ||
       !recovery_field(&attempt,0,"operation",operation) ||
       recovery_integer(&attempt,recovery_json_get(&attempt,0,"timing"),"deadline_ns")!=validation_current_deadline())return 1;
    if(enrollment) {
        RecoveryJson policy;char expected[PATH_MAX];
        if(!recovery_json_document(&policy,approved_persistent_binding) ||
           !recovery_string(&policy,recovery_json_get(&policy,0,"enrollment"),"path",expected,sizeof(expected)) ||
           strcmp(destination,expected) ||
           mkdirat(admission_descriptor,"controlled-setup-v1",0700)!=0)return 1;
    } else {
        char expected[PATH_MAX];snprintf(expected,sizeof(expected),"%s/controlled-setup-v1/stale-control.original",admission_anchor);
        if(strcmp(destination,expected) || !setup_absence(control,1,pid))return 1;
    }
    int directory=openat(admission_descriptor,"controlled-setup-v1",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(directory<0)return 1;
    ok=setup_bound(directory) && fsync(admission_descriptor)==0 &&
        setup_exclusive(directory,enrollment?"enrollment.intent.json":"stale-control.intent.json",attempt_raw);
    if(ok && enrollment) {
        char expected[PATH_MAX];snprintf(expected,sizeof(expected),"%s/",admission_anchor);
        const char *name=destination+strlen(expected);
        if(strncmp(destination,expected,strlen(expected)) || !*name || strchr(name,'/'))ok=0;
        int fd=ok?openat(admission_descriptor,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600):-1;
        if(fd<0)ok=0;
        size_t used=0,size=strlen(raw);
        while(ok && used<size) {
            if(!setup_bound(directory)){ok=0;break;}
            ssize_t count=write(fd,raw+used,size-used);
            if(count<0 && errno==EINTR)continue;if(count<=0){ok=0;break;}used+=(size_t)count;
        }
        if(fd>=0){if(ok && fsync(fd)!=0)ok=0;if(close(fd)!=0)ok=0;}
        char observed[NATIVE_DOCUMENT_BYTES];
        ok=ok && fsync(admission_descriptor)==0 && native_read(admission_descriptor,name,observed,sizeof(observed)) &&
            !strcmp(raw,observed) && setup_bound(directory);
    } else if(ok) {
        ok=setup_exclusive(directory,"stale-control.original",raw) && setup_absence(control,1,pid);
        struct stat current;
        if(ok)ok=fstatat(admission_descriptor,"browser-backend-v1.control",&current,AT_SYMLINK_NOFOLLOW)==0 &&
            native_same_file(&original,&current);
        if(ok)ok=unlinkat(admission_descriptor,"browser-backend-v1.control",0)==0 && fsync(admission_descriptor)==0;
        if(ok)ok=fstatat(admission_descriptor,"browser-backend-v1.control",&current,AT_SYMLINK_NOFOLLOW)!=0 && errno==ENOENT;
    }
    if(ok)ok=setup_bound(directory);if(close(directory)!=0)ok=0;
    if(ok)ok=validation_permitted() && admission_still_bound();
    if(!ok)return 1;
    puts("PREPARATION_ONLY_PENDING_EXACT_REVIEW");return 0;
}


static int native_select_installed(void) {
    const char *injected[]={"KRONOS_NATIVE_SELECTION_PATH","KRONOS_NATIVE_SELECTION_BYTES","KRONOS_NATIVE_SELECTION_SHA256","KRONOS_NATIVE_SELECTION_ID"};
    for(size_t i=0;i<4;i++)if(getenv(injected[i]))return 0;
    RecoveryJson policy,activation;char digest[65],expected[PATH_MAX],path[PATH_MAX],raw[NATIVE_DOCUMENT_BYTES];
    if(!approved_ordinary_restart_policy || !approved_persistent_binding || !initialization_policy() ||
       !recovery_json_document(&policy,approved_ordinary_restart_policy) || policy.token[0].count!=7 ||
       !recovery_field(&policy,0,"schema","ORDINARY_SAME_RELEASE_V1") ||
       !recovery_field(&policy,0,"scope","ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP") ||
       !recovery_field(&policy,0,"installation_identity",native_journal.installation))return 0;
    native_digest(approved_persistent_binding,strlen(approved_persistent_binding),digest);
    if(!recovery_field(&policy,0,"binding_sha256",digest))return 0;
    native_digest(initialization_policy(),strlen(initialization_policy()),digest);
    if(!recovery_field(&policy,0,"genesis_disposition_sha256",digest))return 0;
    if(snprintf(expected,sizeof(expected),"%s/ordinary-start-v1/installed-selection.json",admission_anchor)>=(int)sizeof(expected) ||
       !recovery_field(&policy,0,"installed_selection_path",expected) ||
       snprintf(path,sizeof(path),"%s/ordinary-start-v1/activation.json",admission_anchor)>=(int)sizeof(path) ||
       !recovery_read_file(path,raw,sizeof(raw),1) || !recovery_json_document(&activation,raw) ||
       activation.token[0].count!=9 || !recovery_field(&activation,0,"schema","KRONOS_ORDINARY_ACTIVATION_V1") ||
       !recovery_field(&activation,0,"installation_identity",native_journal.installation))return 0;
    native_digest(approved_ordinary_restart_policy,strlen(approved_ordinary_restart_policy),digest);
    int selected=recovery_json_get(&activation,0,"selection");
    if(!recovery_field(&activation,0,"policy_sha256",digest) ||
       !recovery_field(&activation,selected,"path",expected) ||
       !native_copy_json(&activation,selected,native_startup.selected,sizeof(native_startup.selected)))return 0;
    char observed[NATIVE_DOCUMENT_BYTES];
    return initialization_reference(&activation,selected,expected,observed) && validation_permitted();
}

static int native_stop_budget(void) {
    const char *deadline=getenv("KRONOS_ORDINARY_STOP_DEADLINE_NS"),*boot=getenv("KRONOS_ORDINARY_STOP_BOOT_SESSION");
    char observed[37];long long now=validation_now_ns();
    if(!deadline || !*deadline || strlen(deadline)>19 || strspn(deadline,"0123456789")!=strlen(deadline) ||
       !boot || !current_boot_identity(observed) || strcmp(boot,observed))return 0;
    errno=0;char *end;long long original=strtoll(deadline,&end,10);
    if(errno || *end || !now || original<=now || original-now>15000000000LL)return 0;
    if(!validation_deadline_ns || original<validation_deadline_ns)validation_deadline_ns=original;
    return operation_boot_bound() && validation_permitted();
}
static int native_ordinary_stop(const char *repository,const char *python,const char *control) {
    (void)repository;(void)python;
    char token[65],generation[65],identity[100],details[160],expected_birth[65];pid_t backend;
    if(!native_select_installed() || !recovery_control_record(control,&backend,token) || backend!=getppid() ||
       !native_process_birth(backend,expected_birth))return 1;
    const char *requested_generation=getenv("KRONOS_ORDINARY_STOP_GENERATION");
    if(!requested_generation || !valid_token(requested_generation))return 1;
    strcpy(generation,requested_generation);
    snprintf(identity,sizeof(identity),"stop-%.48s",generation);
    long long stop=validation_now_ns()+15000000000LL;
    if(validation_deadline_ns && validation_deadline_ns<stop)stop=validation_deadline_ns;
    validation_deadline_ns=stop;stop_deadline_ns=stop;
    snprintf(details,sizeof(details),"{\"generation\":\"%s\"}",generation);
    if(!native_validation("ordinary-stop-reserve",identity,details,1) || !native_apply_proposal())return 1;
    snprintf(ordinary_stop_header,sizeof(ordinary_stop_header),"X-Kronos-Ordinary-Stop: %s\r\n",identity);
    if(!request_graceful_shutdown_effect(backend,token,generation,1)) {
        validation_outcome("ORDINARY_STOP",validation_current_deadline(),0,"STOP_REQUEST_DENIED",validation_has_unresolved());return 1;
    }
    memset(token,0,sizeof(token));
    int terminal=0;
    while(validation_permitted()) {
        struct proc_bsdinfo info;memset(&info,0,sizeof(info));
        int found=proc_pidinfo(backend,PROC_PIDTBSDINFO,0,&info,sizeof(info));
        if(found==0 && errno==ESRCH) {terminal=1;break;}
        if(found!=(int)sizeof(info))return 1;
        char birth[65];if(!native_birth_digest(info.pbi_start_tvsec,info.pbi_start_tvusec,birth) ||
           strcmp(birth,expected_birth))return 1;
        struct timespec delay={.tv_sec=0,.tv_nsec=10000000};nanosleep(&delay,NULL);
    }
    if(!terminal || !validation_permitted())return 1;
    int socket=connect_backend();if(socket>=0){close(socket);return 1;}
    struct stat st;if(lstat(control,&st)==0 || errno!=ENOENT || !recovery_listener_scan(0,1))return 1;
    if(!native_validation("ordinary-stop-terminal",identity,"{}",1) || validation_has_unresolved())return 1;
    RecoveryJson result;char raw[NATIVE_DOCUMENT_BYTES],name[240];
    if(!recovery_json_document(&result,native_startup.last_result) ||
       !native_copy_json(&result,recovery_json_get(&result,0,"terminal"),raw,sizeof(raw)))return 1;
    snprintf(name,sizeof(name),"%s.terminal.json",identity);
    if(!native_exclusive(name,raw))return 1;
    /* The head deliberately remains STOP_INTENT. This acknowledgement cannot
     * authorize a child. One new reserved attempt must check current facts. */
    puts("ORDINARY_STOP_PREPARED_CURRENT_CHECK_REQUIRED");return 0;
}

int main(void) {
    const char *mode = getenv("KRONOS_LAUNCH_MODE");
    /* Signed-package execution check: no filesystem, runtime, or Browser action. */
    if (mode != NULL && strcmp(mode, "PACKAGE_VERIFY") == 0) {
        puts("KRONOS_LAUNCHER_PACKAGE_V1_OK");
        return 0;
    }
    validation_deadline_ns=validation_now_ns();if(!validation_deadline_ns)return 1;
    validation_deadline_ns+=120000000000LL;
    struct timespec pretransition_io_deadline={
        .tv_sec=(time_t)(validation_deadline_ns/1000000000LL),
        .tv_nsec=(long)(validation_deadline_ns%1000000000LL)};
    recovery_io_deadline=&pretransition_io_deadline;
    if (!canonical_operational_image()) return 1;
    int bootstrap = mode != NULL && strcmp(mode, "LEGACY_BOOTSTRAP") == 0;
    int replacement = mode != NULL && strcmp(mode, "GOVERNED_REPLACEMENT") == 0;
    int recovery = mode != NULL && strcmp(mode, RECOVERY_CLASS) == 0;
    int restoration = mode != NULL && strcmp(mode, "FAILED_SUCCESSOR_RESTORATION") == 0;
    int initialization = mode != NULL && strcmp(mode,"ADMISSION_HEAD_INITIALIZATION")==0;
    int setup = mode != NULL && strcmp(mode,"CONTROLLED_INSTALLATION_SETUP")==0;
    const char *recovery_attempt = getenv("KRONOS_RECOVERY_ATTEMPT");
    const char *target_revision = getenv("KRONOS_REPLACEMENT_REVISION");
    const char *migration = getenv("KRONOS_LEGACY_BOOTSTRAP_ID");
    const char *migration_proof = getenv("KRONOS_LEGACY_BOOTSTRAP_PROOF");
    int ordinary_stop=(mode!=NULL && strcmp(mode,"ORDINARY_STOP")==0);
    if(ordinary_stop && !native_stop_budget())return 1;
    if(!ordinary_stop && (getenv("KRONOS_ORDINARY_STOP_GENERATION") ||
       getenv("KRONOS_ORDINARY_STOP_DEADLINE_NS") || getenv("KRONOS_ORDINARY_STOP_BOOT_SESSION")))return 1;
    if ((mode != NULL && !bootstrap && !replacement && !recovery && !restoration && !initialization && !setup && !ordinary_stop) ||
        (!bootstrap && (migration != NULL || migration_proof != NULL))) return 1;
    if (bootstrap && (migration == NULL || migration_proof == NULL ||
        strlen(migration) != 64 || strlen(migration_proof) != 64 ||
        strspn(migration, "0123456789abcdef") != 64 ||
        strspn(migration_proof, "0123456789abcdef") != 64 ||
        getenv("KRONOS_MAINTENANCE_GENERATION") != NULL ||
        getenv("KRONOS_MAINTENANCE_PARENT") != NULL ||
        getenv("KRONOS_MAINTENANCE_PROOF") != NULL ||
        getenv("KRONOS_MAINTENANCE_PROTOCOL") != NULL ||
        getenv("KRONOS_MAINTENANCE_REVISION") != NULL)) return 1;
    if (
        (replacement && (
            !valid_revision(target_revision) ||
            migration != NULL || migration_proof != NULL ||
            getenv("KRONOS_MAINTENANCE_GENERATION") != NULL ||
            getenv("KRONOS_MAINTENANCE_PARENT") != NULL ||
            getenv("KRONOS_MAINTENANCE_PROOF") != NULL
            || getenv("KRONOS_MAINTENANCE_PROTOCOL") != NULL
            || getenv("KRONOS_MAINTENANCE_REVISION") != NULL
        )) ||
        (!replacement && !recovery && target_revision != NULL) ||
        (recovery && (!valid_token(recovery_attempt) || !valid_revision(target_revision) || bootstrap ||
            migration != NULL || migration_proof != NULL || getenv("KRONOS_MAINTENANCE_GENERATION") != NULL ||
            getenv("KRONOS_MAINTENANCE_PARENT") != NULL || getenv("KRONOS_MAINTENANCE_PROOF") != NULL ||
            getenv("KRONOS_MAINTENANCE_PROTOCOL") != NULL || getenv("KRONOS_MAINTENANCE_REVISION") != NULL)) ||
        (!recovery && recovery_attempt != NULL)
    ) return 1;
    /* These are child-only locators derived from the native-selected records.
     * A caller cannot select another claim or mix restoration with V1/V2. */
    extern char **environ;
    for(char **item=environ;*item;item++)
        if(!strncmp(*item,"KRONOS_RESTORATION_",19) || !strncmp(*item,"KRONOS_NATIVE_ATTEMPT_",22) ||
           !strncmp(*item,"KRONOS_NATIVE_HEAD_SHA256=",26) ||
           (!initialization && !strncmp(*item,"KRONOS_INITIALIZATION_",22)) ||
           (!setup && !strncmp(*item,"KRONOS_SETUP_",13)))return 1;
    if(restoration && (getenv("KRONOS_MAINTENANCE_GENERATION") || getenv("KRONOS_MAINTENANCE_PARENT") ||
       getenv("KRONOS_MAINTENANCE_PROOF") || getenv("KRONOS_MAINTENANCE_PROTOCOL") || getenv("KRONOS_MAINTENANCE_REVISION")))return 1;
    if((initialization || setup) && (getenv("KRONOS_MAINTENANCE_GENERATION") || getenv("KRONOS_MAINTENANCE_PARENT") ||
       getenv("KRONOS_MAINTENANCE_PROOF") || getenv("KRONOS_MAINTENANCE_PROTOCOL") || getenv("KRONOS_MAINTENANCE_REVISION")))return 1;
    if(!mode || ordinary_stop) {
        const char *names[]={"KRONOS_NATIVE_SELECTION_PATH","KRONOS_NATIVE_SELECTION_BYTES","KRONOS_NATIVE_SELECTION_SHA256","KRONOS_NATIVE_SELECTION_ID"};
        for(size_t i=0;i<4;i++)if(getenv(names[i]))return 1;
    }
    const char *home = getenv("HOME");
    if (home == NULL || home[0] == '\0') return (initialization || setup)?1:show_not_ready();

    char repository[PATH_MAX];
    char python[PATH_MAX];
    char browser_entry[PATH_MAX];
    char python_path[PATH_MAX * 2];
    char control_path[PATH_MAX];
    if (
        !discover_repository(home, repository) ||
        snprintf(python, sizeof(python), "%s/.venv/bin/python", repository) < 0 ||
        snprintf(browser_entry, sizeof(browser_entry), "%s/tools/kronos_browser.py", repository) < 0 ||
        snprintf(python_path, sizeof(python_path), "%s/src:%s", repository, repository) < 0 ||
        snprintf(
            control_path,
            sizeof(control_path),
            "%s/Library/Application Support/KRONOS/runtime/browser-backend-v1.control",
            home
        ) < 0
    ) {
        return (initialization || setup)?1:show_not_ready();
    }
    if (access(python, X_OK) != 0 || access(browser_entry, R_OK) != 0) {
        return (initialization || setup)?1:show_not_ready();
    }

    /* Acquire installation exclusion BEFORE decisive source admission/effects.
     * Missing approved binding and nonblocking contention both deny. */
    admission_descriptor=acquire_launcher_lock(repository);
    if(admission_descriptor<0)return (initialization || setup)?1:show_alert("KRONOS launch blocked",
        "Approved installation admission custody is unavailable. No runtime transition was started.");

    /* The read-only source gate precedes every probe or runtime transition. */
    if (!qualify_source(repository, python)) return (initialization || setup)?initialization_return(1):show_alert(
        "KRONOS source qualification failed",
        "The clean published maintenance/release-b-swing-ux revision and verified source proof are required. No runtime transition was started. Contact Engineering."
    );
    if(setup)return initialization_return(native_setup(repository,python,control_path));
    if(initialization) {
        int result=native_initialize(repository,python,control_path);
        return initialization_return(result);
    }
    if(!native_gate(repository,python,mode?mode:"ORDINARY"))return show_alert("KRONOS admission blocked",
        "Initialized admission history is missing, inconsistent or unresolved. No runtime transition was started.");
    if ((replacement || recovery) && !repository_revision_matches(repository, target_revision)) {
        return show_alert(
            "KRONOS replacement blocked",
            "The requested replacement revision is not the exact clean published source. No runtime transition was started. Contact Engineering."
        );
    }

    if(ordinary_stop) {int result=native_ordinary_stop(repository,python,control_path);finish_admission();return result;}
    /* An ordinary Dock click is inert access to one already-ready shared runtime. */
    if (!bootstrap && !replacement && !recovery && !restoration && native_reuse(control_path)) return open_workspace();

    if(restoration) {
        int connected=connect_backend();if(connected>=0){close(connected);return show_restart_blocked();}
        struct stat control;
        if(lstat(control_path,&control)==0 || errno!=ENOENT || !recovery_listener_scan(0,1) ||
           !native_select_environment())return show_restart_blocked();
        native_startup.restoration=1;
        if(!native_validation("restoration-reserve","","{}",1) || !native_apply_proposal())return show_restart_blocked();
        BackendStartResult outcome=start_backend(repository,python,browser_entry,python_path,0,"","","");
        switch(outcome) {
            case BACKEND_START_READY:finish_admission();return open_workspace();
            case BACKEND_START_CHILD_EXITED:return show_replacement_child_exited();
            case BACKEND_START_READY_TIMEOUT:return show_replacement_ready_timeout();
            case BACKEND_START_INTERNAL_FAILURE:return show_replacement_internal_failure();
        }
        return show_replacement_internal_failure();
    }

    pid_t backend_pid = 0;
    ReplacementReadiness readiness = REPLACEMENT_NOT_READY;
    char token[65] = {0};
    RecoveryAuthorization recovery_authority;
    if (recovery) {
        char root[PATH_MAX],installed[65],rollback[65],relation[PATH_MAX];
        if (snprintf(root,sizeof(root),"%s/Library/Application Support/KRONOS/runtime/failed-active-recovery-v1",home)>=(int)sizeof(root) ||
            !recovery_control_record(control_path,&backend_pid,token) ||
            !recovery_load_authorization(root,recovery_attempt,control_path,backend_pid,target_revision,recovery_now_us(),&recovery_authority) ||
            (!recovery_authority.swing_incident && (snprintf(relation,sizeof(relation),"%s/Library/Application Support/KRONOS/evidence/intraday-v1/live-shadow-v1/epochs-v1/WO06H-SUCCESSOR_COMPATIBILITY-%s.json",home,
                recovery_authority.historical ? "1a9a7b8b997447716f1b6f11b02fbcccf88fda2644b4a2af23604dbf5f293976" :
                    "4f6aac6c3a9f59fe2e19b788fb6266fec1a239358e71f2abc9f9c9ac4c0731ef")>=(int)sizeof(relation) ||
            strcmp(recovery_authority.relation,relation))) ||
            !recovery_package_identity(repository,python,canonical_bundle,installed) || strcmp(installed,recovery_authority.package) ||
            !recovery_package_identity(repository,python,recovery_authority.rollback,rollback) || strcmp(rollback,recovery_authority.rollback_identity) ||
            !recovery_assess(&recovery_authority,repository,python)) { memset(token,0,sizeof(token));return show_restart_blocked(); }
    }
    if (replacement) {
        if (!read_control_record(control_path, &backend_pid, token)) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        readiness = backend_replacement_readiness(
            backend_pid,
            target_revision
        );
        if (readiness == REPLACEMENT_ALREADY_LOADED) {
            (void)memset(token, 0, sizeof(token));
            return native_reuse(control_path)?open_workspace():show_restart_blocked();
        }
        if (
            readiness != REPLACEMENT_REQUIRED &&
            readiness != REPLACEMENT_REQUIRED_OLD_CF55
        ) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        puts(
            readiness == REPLACEMENT_REQUIRED_OLD_CF55
                ? "KRONOS_REPLACEMENT_PREDICATE=OLD_RUNTIME_CF55_STATUS_PAIR"
                : "KRONOS_REPLACEMENT_PREDICATE=CURRENT_RUNTIME_STATUS"
        );
        (void)fflush(stdout);
    }
    char generation[65] = {0};
    char predecessor_revision[41] = {0};
    if (recovery) strcpy(predecessor_revision,recovery_authority.predecessor);
    if (replacement && readiness == REPLACEMENT_REQUIRED) {
        char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
        if (!read_backend_route("/runtime/status", response) ||
            !runtime_process_revision(response, backend_pid, predecessor_revision) ||
            strcmp(predecessor_revision, target_revision) == 0 ||
            !new_runtime_is_drainable(response)) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
    }
    unsigned char random_bytes[32];
    arc4random_buf(random_bytes, sizeof(random_bytes));
    for (size_t i = 0; i < sizeof(random_bytes); ++i)
        (void)snprintf(generation + i * 2, 3, "%02x", random_bytes[i]);
    if(!admission_still_bound())return show_restart_blocked();
    int socket_connected = connect_backend();
    if (socket_connected >= 0) {
        (void)close(socket_connected);
        if (!bootstrap && !replacement && !recovery) return show_existing_backend_unhealthy();
        if (replacement && readiness == REPLACEMENT_REQUIRED_OLD_CF55) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        if (
            (!replacement && !recovery && !read_control_record(control_path, &backend_pid, token)) ||
            (recovery && (!recovery_continuity(repository,python,home,NULL) ||
                !recovery_assess(&recovery_authority,repository,python) ||
                !recovery_bindings_match(&recovery_authority,repository,python,token))) ||
            !native_original_reserve(backend_pid) || !native_dispatch_intent(control_path,generation) ||
            (recovery && !recovery_reserve(&recovery_authority,generation,recovery_now_us())) ||
            !admission_still_bound() ||
            !request_graceful_shutdown(backend_pid, token, generation, replacement || recovery) ||
            !wait_for_backend_stop(backend_pid)
        ) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        if ((replacement || recovery) && !verify_v2_handoff(repository, python, python_path,
                control_path, generation, backend_pid, predecessor_revision, token)) {
            (void)memset(token, 0, sizeof(token));
            return show_restart_blocked();
        }
        if(!native_retired(home,generation)){memset(token,0,sizeof(token));return show_restart_blocked();}
    } else if (replacement || recovery) {
        (void)memset(token, 0, sizeof(token));
        return show_restart_blocked();
    } else if (!bootstrap && !recovery && !cold_start_has_no_control_or_live_handoff(control_path)) {
        return show_existing_backend_unhealthy();
    }
    if(!native_startup.active && !native_original_reserve(0))return show_restart_blocked();

    if (recovery) {
        if (!recovery_continuity(repository,python,home,generation) ||
            !recovery_bindings_match(&recovery_authority,repository,python,NULL) ||
            !recovery_attempt_matches(&recovery_authority,generation) ||
            !verify_v2_handoff(repository,python,python_path,control_path,generation,backend_pid,predecessor_revision,token) ||
            kill(backend_pid,0)==0 || errno!=ESRCH) {
            memset(token,0,sizeof(token));return show_restart_blocked();
        }
        if(!recovery_listener_scan(0,1)){memset(token,0,sizeof(token));return show_restart_blocked();}
        long long final_now=recovery_now_us();
        if(!recovery_time_valid(&recovery_authority,final_now)){
            memset(token,0,sizeof(token));return show_restart_blocked();}
        recovery_successor=(RecoverySuccessorContext){.authority=&recovery_authority,
            .repository=repository,.python=python,.generation=generation,.home=home};
    }
    BackendStartResult start_result = start_backend(
        repository,
        python,
        browser_entry,
        python_path,
        backend_pid,
        token,
        generation,
        predecessor_revision
    );
    (void)memset(token, 0, sizeof(token));
    switch (start_result) {
        case BACKEND_START_READY:
            finish_admission();
            return bootstrap ? 0 : open_workspace();
        case BACKEND_START_CHILD_EXITED:
            return show_replacement_child_exited();
        case BACKEND_START_READY_TIMEOUT:
            return show_replacement_ready_timeout();
        case BACKEND_START_INTERNAL_FAILURE:
            return show_replacement_internal_failure();
    }
    return show_replacement_internal_failure();
}
