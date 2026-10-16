#import <Cocoa/Cocoa.h>
#import <CommonCrypto/CommonDigest.h>
#import <sys/file.h>
#import <sys/stat.h>
#import <sys/socket.h>
#import <netinet/in.h>
#import <arpa/inet.h>
#import <signal.h>
#import <fcntl.h>
#import <unistd.h>
#import <errno.h>
#import <dispatch/dispatch.h>

// Synthetic adapter only. No personal-source, credential, MCP, or AI client is loaded.
static NSString * const XSFixture = @"synthetic:fixture-v1";
static NSString * const XSPurpose = @"package-lifecycle-test";
static NSData *Encode(id value) { return [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:nil]; }
static NSString *Hash(NSData *data) {
    unsigned char h[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,h);
    NSMutableString *s=[NSMutableString string]; for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++) [s appendFormat:@"%02x",h[i]]; return s;
}
static void Fail(NSString *code) { @throw [NSException exceptionWithName:@"XSClosed" reason:code userInfo:nil]; }
static BOOL ExactKeys(NSDictionary *d, NSArray *keys) { return [d isKindOfClass:NSDictionary.class] && [[NSSet setWithArray:d.allKeys] isEqual:[NSSet setWithArray:keys]]; }
static BOOL Integer(id v) { return [v isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)v)!=CFBooleanGetTypeID() && [v doubleValue]>=0 && [v doubleValue]<=1000000000000.0 && floor([v doubleValue])==[v doubleValue]; }
static NSDictionary *Result(NSString *code) { return @{@"code":code,@"synthetic_only":@YES,@"real_source_access":@NO}; }
static void PrintJSON(id value) { NSData *d=Encode(value);if(!d || fwrite(d.bytes,1,d.length,stdout)!=d.length || fputc('\n',stdout)==EOF || fflush(stdout)!=0)Fail(@"DISCLOSURE_CHANNEL_FAILED"); }

@interface XSRunner : NSObject
@property(copy) NSString *root;
@property(copy) NSString *session;
@property(copy) NSString *token;
@property BOOL started;
@property(strong) NSArray *stateKeys;
@property(strong) dispatch_semaphore_t reservationBarrier;
@property(strong) dispatch_semaphore_t publicationBarrier;
@property(copy) void (^disclosureSink)(NSDictionary *);
- (NSDictionary *)status;
- (NSDictionary *)start;
- (NSDictionary *)grant:(double)ttl;
- (NSDictionary *)readFixture:(useconds_t)delay;
- (NSDictionary *)revoke:(BOOL)stop;
@end

@implementation XSRunner
- (instancetype)init {
    if((self=[super init])) {
        NSString *run=NSBundle.mainBundle.infoDictionary[@"XSTestRunID"];
        if(![run isKindOfClass:NSString.class] || run.length!=32 || [run rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet]].location!=NSNotFound) Fail(@"INVALID_TEST_NAMESPACE");
        self.root=[NSHomeDirectory() stringByAppendingPathComponent:[@"Library/Application Support/XINGSHULocalRunner" stringByAppendingPathComponent:run]];
        self.session=NSUUID.UUID.UUIDString; self.token=@""; self.started=NO;
        self.stateKeys=@[@"version",@"generation",@"epoch",@"ready",@"runner_pid",@"runner_session",@"progress",@"reads",@"authority"];
        NSError *e=nil; if(![NSFileManager.defaultManager createDirectoryAtPath:self.root withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:&e]) Fail(@"STATE_DIRECTORY_UNAVAILABLE");
        // Reject symlinks in every existing state-directory component.
        NSString *part=@"/"; struct stat st;
        for(NSString *c in self.root.pathComponents) { if([c isEqual:@"/"])continue; part=[part stringByAppendingPathComponent:c]; if(lstat(part.fileSystemRepresentation,&st)!=0 || !S_ISDIR(st.st_mode) || S_ISLNK(st.st_mode)) Fail(@"UNSAFE_STATE_DIRECTORY"); }
    } return self;
}
- (NSMutableDictionary *)blankAuthority { return [@{@"status":@"inactive",@"token_hash":@"",@"receiver_pid":@0,@"session":@"",@"source":XSFixture,@"purpose":XSPurpose,@"expires":@0,@"remaining":@0} mutableCopy]; }
- (NSMutableDictionary *)initialState { return [@{@"version":@1,@"generation":@0,@"epoch":@0,@"ready":@NO,@"runner_pid":@0,@"runner_session":@"",@"progress":@"idle",@"reads":@0,@"authority":[self blankAuthority]} mutableCopy]; }
- (void)check:(NSDictionary *)s {
    if(!ExactKeys(s,self.stateKeys) || !Integer(s[@"version"]) || ![s[@"version"] isEqual:@1]) Fail(@"STATE_SCHEMA_INVALID");
    for(NSString *k in @[@"generation",@"epoch",@"runner_pid",@"reads"]) if(!Integer(s[k])) Fail(@"STATE_SCHEMA_INVALID");
    if(CFGetTypeID((__bridge CFTypeRef)s[@"ready"])!=CFBooleanGetTypeID() || ![s[@"runner_session"] isKindOfClass:NSString.class] || ![@[@"idle",@"started",@"read_complete",@"awaiting_resume"] containsObject:s[@"progress"]]) Fail(@"STATE_SCHEMA_INVALID");
    NSDictionary *a=s[@"authority"];
    if(!ExactKeys(a,@[@"status",@"token_hash",@"receiver_pid",@"session",@"source",@"purpose",@"expires",@"remaining"]) || ![@[@"inactive",@"active",@"reserved",@"consumed",@"revoked",@"failed"] containsObject:a[@"status"]] || ![a[@"source"] isEqual:XSFixture] || ![a[@"purpose"] isEqual:XSPurpose] || !Integer(a[@"receiver_pid"]) || !Integer(a[@"remaining"]) || [a[@"remaining"] intValue]>1 || ![a[@"expires"] isKindOfClass:NSNumber.class] || !isfinite([a[@"expires"] doubleValue]) || ![a[@"session"] isKindOfClass:NSString.class] || ![a[@"token_hash"] isKindOfClass:NSString.class]) Fail(@"AUTHORITY_SCHEMA_INVALID");
}
- (NSMutableDictionary *)load:(int)dir {
    int fd=openat(dir,"state.json",O_RDONLY|O_NOFOLLOW|O_NONBLOCK);
    if(fd<0) { if(errno==ENOENT)return [self initialState]; Fail(@"STATE_OPEN_DENIED"); }
    struct stat st; if(fstat(fd,&st)!=0 || !S_ISREG(st.st_mode) || st.st_nlink!=1 || st.st_size>65536) {close(fd);Fail(@"UNSAFE_STATE_FILE");}
    NSMutableData *raw=[NSMutableData data]; char b[4096]; ssize_t n;
    while((n=read(fd,b,sizeof(b)))>0) { [raw appendBytes:b length:(NSUInteger)n]; if(raw.length>65536){close(fd);Fail(@"STATE_TOO_LARGE");} }
    close(fd); if(n<0)Fail(@"STATE_READ_FAILED");
    NSDictionary *e=[NSJSONSerialization JSONObjectWithData:raw options:NSJSONReadingMutableContainers error:nil];
    if(!ExactKeys(e,@[@"digest",@"state"]) || ![Encode(e) isEqualToData:raw] || ![e[@"digest"] isEqual:Hash(Encode(e[@"state"]))]) Fail(@"STATE_INTEGRITY_FAILURE");
    [self check:e[@"state"]]; return e[@"state"];
}
- (void)save:(NSMutableDictionary *)s directory:(int)dir {
    s[@"generation"]=@([s[@"generation"] unsignedLongLongValue]+1); [self check:s];
    NSData *raw=Encode(@{@"digest":Hash(Encode(s)),@"state":s}); if(!raw)Fail(@"STATE_ENCODING_FAILED");
    NSString *tmp=[NSString stringWithFormat:@"state-%@.tmp",NSUUID.UUID.UUIDString];
    int fd=openat(dir,tmp.UTF8String,O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW,0600); if(fd<0)Fail(@"STATE_WRITE_DENIED");
    size_t left=raw.length; const char *ptr=raw.bytes; BOOL ok=YES;
    while(left) {ssize_t n=write(fd,ptr,left);if(n<=0){ok=NO;break;}ptr+=n;left-=(size_t)n;}
    if(fsync(fd)!=0)ok=NO; close(fd);
    if(!ok || renameat(dir,tmp.UTF8String,dir,"state.json")!=0) {unlinkat(dir,tmp.UTF8String,0);Fail(@"STATE_COMMIT_FAILED");}
    if(fsync(dir)!=0)Fail(@"STATE_DIRECTORY_SYNC_FAILED");
}
- (id)transaction:(id(^)(NSMutableDictionary *,int))block {
    int dir=open(self.root.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW); if(dir<0)Fail(@"STATE_ROOT_DENIED");
    int lock=openat(dir,"state.lock",O_CREAT|O_RDWR|O_NOFOLLOW|O_NONBLOCK,0600);struct stat st;
    if(lock<0 || fstat(lock,&st)!=0 || !S_ISREG(st.st_mode) || st.st_nlink!=1) {if(lock>=0)close(lock);close(dir);Fail(@"UNSAFE_STATE_LOCK");}
    if(flock(lock,LOCK_EX)!=0){close(lock);close(dir);Fail(@"STATE_LOCK_FAILED");}
    @try {return block([self load:dir],dir);} @finally {flock(lock,LOCK_UN);close(lock);close(dir);}
}
- (BOOL)ownsSession:(NSDictionary *)s {return self.started && [s[@"ready"] boolValue] && [s[@"runner_pid"] intValue]==getpid() && [s[@"runner_session"] isEqual:self.session];}
- (NSDictionary *)status {
    return [self transaction:^id(NSMutableDictionary *s,int dir) {
        (void)dir; NSDictionary *a=s[@"authority"]; BOOL mine=[self ownsSession:s];
        NSDictionary *handoff=@{@"schema_version":@"0.2",@"task_id":@"XS-LOCAL-RUNNER-TEST",@"status":mine?@"RUNNING":@"READY",@"canonical_state_report":@"fixture://authority/XS-LOCAL-RUNNER-TEST",@"current_artifact":@"fixture://artifact/local-runner-candidate",@"artifact_type":@"TEST_EVIDENCE",@"next_actor":@"CODEX",@"owner_required":@NO,@"blocked":@NO,@"context_remaining_percent":NSNull.null,@"timestamp":[NSISO8601DateFormatter.new stringFromDate:NSDate.date]};
        return @{@"code":@"STATUS",@"synthetic_only":@YES,@"running_in_this_process":@(mine),@"pid":@(getpid()),@"state_path":[self.root stringByAppendingPathComponent:@"state.json"],@"task_progress":s[@"progress"],@"reads":s[@"reads"],@"authority_status":a[@"status"],@"usable_in_this_process":@((BOOL)(mine && self.token.length>0 && [a[@"status"] isEqual:@"active"] && [a[@"expires"] doubleValue]>NSDate.date.timeIntervalSince1970)),@"real_ai_connected":@NO,@"p5_connected":@NO,@"openwiki_connected":@NO,@"background_helpers":@0,@"handoff":handoff};
    }];
}
- (NSDictionary *)start {
    return [self transaction:^id(NSMutableDictionary *s,int dir) {
        if([self ownsSession:s])return Result(@"ALREADY_STARTED");
        int other=[s[@"runner_pid"] intValue];
        if([s[@"ready"] boolValue] && other>0 && other!=getpid()) {errno=0; if(kill(other,0)==0 || errno!=ESRCH)Fail(@"OTHER_SESSION_ACTIVE_OR_UNKNOWN");}
        self.started=YES;self.token=@"";s[@"ready"]=@YES;s[@"runner_pid"]=@(getpid());s[@"runner_session"]=self.session;if([s[@"progress"] isEqual:@"idle"])s[@"progress"]=@"started";s[@"epoch"]=@([s[@"epoch"] longLongValue]+1);s[@"authority"]=[self blankAuthority]; [self save:s directory:dir];return Result(@"STARTED");
    }];
}
- (NSDictionary *)grant:(double)ttl {
    if(!isfinite(ttl)||ttl<=0||ttl>60)Fail(@"INVALID_TEST_TTL");
    return [self transaction:^id(NSMutableDictionary *s,int dir) {
        if(![self ownsSession:s])Fail(@"NOT_RUNNING");
        NSDictionary *old=s[@"authority"];if([@[@"active",@"reserved"] containsObject:old[@"status"]] && [old[@"expires"] doubleValue]>NSDate.date.timeIntervalSince1970)Fail(@"TEST_AUTHORITY_ALREADY_ACTIVE");
        self.token=NSUUID.UUID.UUIDString;s[@"authority"]=[@{@"status":@"active",@"token_hash":Hash([self.token dataUsingEncoding:NSUTF8StringEncoding]),@"receiver_pid":@(getpid()),@"session":self.session,@"source":XSFixture,@"purpose":XSPurpose,@"expires":@(NSDate.date.timeIntervalSince1970+ttl),@"remaining":@1} mutableCopy]; [self save:s directory:dir];return Result(@"TEST_ONLY_GRANTED_ONCE");
    }];
}
- (NSDictionary *)readFixture:(useconds_t)delay {
    if(!self.disclosureSink)Fail(@"NO_DISCLOSURE_SINK");
    __block long long epoch=0; __block NSString *tokenHash=nil;
    [self transaction:^id(NSMutableDictionary *s,int dir) {
        NSMutableDictionary *a=s[@"authority"];tokenHash=Hash([self.token dataUsingEncoding:NSUTF8StringEncoding]);
        if(![self ownsSession:s] || !self.token.length || ![a[@"status"] isEqual:@"active"] || [a[@"remaining"] intValue]!=1 || [a[@"receiver_pid"] intValue]!=getpid() || ![a[@"session"] isEqual:self.session] || ![a[@"token_hash"] isEqual:tokenHash] || [a[@"expires"] doubleValue]<=NSDate.date.timeIntervalSince1970)Fail(@"READ_DENIED");
        epoch=[s[@"epoch"] longLongValue];a[@"remaining"]=@0;a[@"status"]=@"reserved";[self save:s directory:dir];return @YES;
    }];
    @try {
        if(self.reservationBarrier)dispatch_semaphore_signal(self.reservationBarrier);
        NSString *file=[NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"fixture.md"];
        int fd=open(file.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)Fail(@"FIXTURE_UNAVAILABLE");
        struct stat st;if(fstat(fd,&st)!=0||!S_ISREG(st.st_mode)||st.st_nlink!=1||st.st_size>4096){close(fd);Fail(@"FIXTURE_BOUNDARY_FAILURE");}
        NSMutableData *data=[NSMutableData data];char b[4096];ssize_t n;
        while((n=read(fd,b,sizeof(b)))>0){[data appendBytes:b length:(NSUInteger)n];if(data.length>4096){close(fd);Fail(@"FIXTURE_TOO_LARGE");}} close(fd);if(n<0)Fail(@"FIXTURE_READ_FAILED");
        NSString *hash=Hash(data);if(![hash isEqual:NSBundle.mainBundle.infoDictionary[@"XSFixtureSHA256"]])Fail(@"FIXTURE_CHANGED");
        if(delay)usleep(delay);
        return [self transaction:^id(NSMutableDictionary *s,int dir) {
            NSMutableDictionary *a=s[@"authority"];
            if(![self ownsSession:s]||[s[@"epoch"] longLongValue]!=epoch||![a[@"status"] isEqual:@"reserved"]||![a[@"token_hash"] isEqual:tokenHash]||[a[@"expires"] doubleValue]<=NSDate.date.timeIntervalSince1970)Fail(@"REVOKED_BEFORE_DISCLOSURE");
            // The synchronous sink runs while the same lock still excludes revocation.
            // A successful revoke can return only after any prior committed disclosure.
            if(self.publicationBarrier){dispatch_semaphore_signal(self.publicationBarrier);usleep(150000);}
            if([a[@"expires"] doubleValue]<=NSDate.date.timeIntervalSince1970)Fail(@"EXPIRED_BEFORE_DISCLOSURE");
            NSDictionary *payload=@{@"event":@"FIXTURE_DISCLOSURE",@"synthetic_only":@YES,@"source_id":XSFixture,@"purpose":XSPurpose,@"citation":@"bundle://fixture.md",@"sha256":hash,@"emitted_at":@([NSDate.date timeIntervalSince1970]),@"content":[[NSString alloc]initWithData:data encoding:NSUTF8StringEncoding]?:@""};
            self.disclosureSink(payload);
            a[@"status"]=@"consumed";s[@"reads"]=@([s[@"reads"] longLongValue]+1);s[@"progress"]=@"read_complete";[self save:s directory:dir];self.token=@"";
            return @{@"code":@"FIXTURE_READ_OK",@"synthetic_only":@YES,@"real_source_access":@NO,@"source_id":XSFixture,@"purpose":XSPurpose,@"citation":@"bundle://fixture.md",@"sha256":hash};
        }];
    } @catch(NSException *e) {self.token=@"";@throw e;}
}
- (NSDictionary *)revoke:(BOOL)stop {
    return [self transaction:^id(NSMutableDictionary *s,int dir) {
        s[@"epoch"]=@([s[@"epoch"] longLongValue]+1);NSMutableDictionary *a=s[@"authority"];a[@"status"]=@"revoked";a[@"remaining"]=@0;a[@"token_hash"]=@"";self.token=@"";
        if(stop){s[@"ready"]=@NO;self.started=NO;} [self save:s directory:dir];return Result(stop?@"STOPPED_AND_REVOKED":@"REVOKED");
    }];
}
@end

static NSDictionary *Attempt(NSDictionary *(^block)(void)) { @try{return block();}@catch(NSException *e){return Result([e.name isEqual:@"XSClosed"]?e.reason:@"UNEXPECTED_FAILURE_CLOSED");} }
static NSDictionary *Probe(void) {
    NSDictionary *p=NSBundle.mainBundle.infoDictionary;NSString *outside=p[@"XSOutsideCanary"];NSString *writePath=p[@"XSOutsideWrite"];
    errno=0;int fd=open(outside.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW);int re=errno;BOOL rd=fd<0&&(re==EPERM||re==EACCES);if(fd>=0)close(fd);
    errno=0;fd=open(writePath.fileSystemRepresentation,O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW,0600);int we=errno;BOOL wd=fd<0&&(we==EPERM||we==EACCES);if(fd>=0)close(fd);
    errno=0;int sock=socket(AF_INET,SOCK_STREAM,0);int ne=errno;int rc=-1;
    if(sock>=0){struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_port=htons([p[@"XSLoopbackPort"] intValue]);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);rc=connect(sock,(struct sockaddr*)&a,sizeof(a));ne=errno;close(sock);}
    BOOL nd=rc<0&&(ne==EPERM||ne==EACCES);
    return @{@"code":@"SANDBOX_PROBE",@"pid":@(getpid()),@"external_read_denied":@(rd),@"external_read_errno":@(re),@"external_write_denied":@(wd),@"external_write_errno":@(we),@"socket_created":@((BOOL)(sock>=0)),@"connect_attempted":@((BOOL)(sock>=0)),@"connect_result":@(rc),@"loopback_denied":@(nd),@"loopback_errno":@(ne),@"actual_restrictions_pass":@((BOOL)(rd&&wd&&nd&&sock>=0)),@"synthetic_only":@YES};
}

static NSDictionary *Scenario(XSRunner *r,NSString *name) {
    NSMutableArray *events=[NSMutableArray array];
    if([name isEqual:@"lifecycle"]){
        [events addObject:Attempt(^{return [r readFixture:0];})];[events addObject:Attempt(^{return [r start];})];
        [events addObject:Attempt(^{return [r readFixture:0];})];[events addObject:Attempt(^{return [r grant:60];})];
        [events addObject:Attempt(^{return [r readFixture:0];})];[events addObject:Attempt(^{return [r readFixture:0];})];
        [events addObject:Attempt(^{return [r grant:60];})];[events addObject:Attempt(^{return [r revoke:NO];})];
        [events addObject:Attempt(^{return [r readFixture:0];})];[events addObject:Attempt(^{return [r revoke:YES];})];
        [events addObject:Attempt(^{return [r readFixture:0];})];
    }else if([name isEqual:@"concurrent"]){
        [r start];[r grant:60];dispatch_group_t g=dispatch_group_create();
        for(int i=0;i<2;i++)dispatch_group_async(g,dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{@autoreleasepool{NSDictionary *e=Attempt(^{return [r readFixture:0];});@synchronized(events){[events addObject:e];}}});
        dispatch_group_wait(g,DISPATCH_TIME_FOREVER);[r revoke:YES];
    }else if([name isEqual:@"revoke-inflight"]){
        [r start];[r grant:60];r.reservationBarrier=dispatch_semaphore_create(0);dispatch_group_t g=dispatch_group_create();
        dispatch_group_async(g,dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{@autoreleasepool{NSDictionary *e=Attempt(^{return [r readFixture:150000];});@synchronized(events){[events addObject:e];}}});
        if(dispatch_semaphore_wait(r.reservationBarrier,dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC))!=0)Fail(@"RESERVATION_BARRIER_TIMEOUT");[events addObject:[r revoke:NO]];dispatch_group_wait(g,DISPATCH_TIME_FOREVER);r.reservationBarrier=nil;[r revoke:YES];
    }else if([name isEqual:@"expiry"]){[r start];[r grant:0.05];usleep(100000);[events addObject:Attempt(^{return [r readFixture:0];})];[r revoke:YES];
    }else if([name isEqual:@"revoke-at-publication"]){
        [r start];[r grant:60];r.publicationBarrier=dispatch_semaphore_create(0);dispatch_group_t g=dispatch_group_create();
        dispatch_group_async(g,dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{@autoreleasepool{NSDictionary *e=Attempt(^{return [r readFixture:0];});@synchronized(events){[events addObject:e];}}});
        if(dispatch_semaphore_wait(r.publicationBarrier,dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC))!=0)Fail(@"PUBLICATION_BARRIER_TIMEOUT");
        NSMutableDictionary *rev=[[r revoke:NO]mutableCopy];rev[@"returned_at"]=@(NSDate.date.timeIntervalSince1970);@synchronized(events){[events addObject:rev];}dispatch_group_wait(g,DISPATCH_TIME_FOREVER);r.publicationBarrier=nil;
        [events addObject:Attempt(^{return [r readFixture:0];})];[r revoke:YES];
    }else if([name isEqual:@"expire-at-publication"]){[r start];[r grant:0.05];r.publicationBarrier=dispatch_semaphore_create(0);[events addObject:Attempt(^{return [r readFixture:0];})];r.publicationBarrier=nil;[r revoke:YES];
    }else if([name isEqual:@"prepare-reopen"]){[r start];[r grant:60];[r transaction:^id(NSMutableDictionary *s,int dir){s[@"progress"]=@"awaiting_resume";[r save:s directory:dir];return @YES;}];[events addObject:Result(@"PROGRESS_SAVED_AUTHORITY_NOT_EXPORTABLE")];
    }else if([name isEqual:@"after-reopen"]){[events addObject:[r status]];[events addObject:Attempt(^{return [r readFixture:0];})];[r revoke:YES];
    }else if([name isEqual:@"crash"]){[r start];[r grant:60];PrintJSON([r status]);_exit(23);
    }else Fail(@"UNKNOWN_SYNTHETIC_SCENARIO");
    return @{@"code":@"SYNTHETIC_SCENARIO_RESULT",@"scenario":name,@"events":events,@"status":[r status],@"human_approval_proven":@NO,@"real_source_access":@NO,@"formal_A1_accepted":@NO};
}

@interface XSApp : NSObject<NSApplicationDelegate>
@property(strong) NSWindow *window;@property(strong) NSTextField *statusLabel;@property(strong) NSTextView *output;@property(strong) XSRunner *runner;@property(strong) NSTimer *refreshTimer;
@end
@implementation XSApp
- (void)applicationDidFinishLaunching:(NSNotification *)n {
    (void)n;self.runner=[XSRunner new];__weak XSApp *weakSelf=self;self.runner.disclosureSink=^(NSDictionary *payload){XSApp *target=weakSelf;if(!target)Fail(@"RECEIVER_CLOSED");[target presentDisclosure:payload];};
    self.window=[[NSWindow alloc]initWithContentRect:NSMakeRect(0,0,760,520) styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable backing:NSBackingStoreBuffered defer:NO];
    self.window.title=@"星枢本地运行器（假资料测试版）";[self.window center];NSView *v=self.window.contentView;
    NSTextField *title=[NSTextField labelWithString:@"星枢 · 本地运行器"];title.frame=NSMakeRect(28,464,700,32);title.font=[NSFont boldSystemFontOfSize:25];[v addSubview:title];
    NSTextField *note=[NSTextField wrappingLabelWithString:@"仅使用包内假资料，验证启动、读取、接续、停止和撤销。\n真实 AI、个人主库 / P5、OpenWiki：均未连接。不会申请真实资料访问权限。"];
    note.frame=NSMakeRect(28,394,700,58);note.font=[NSFont systemFontOfSize:14];[v addSubview:note];
    self.statusLabel=[NSTextField wrappingLabelWithString:@"当前窗口未启动任务"];self.statusLabel.frame=NSMakeRect(28,350,700,40);self.statusLabel.font=[NSFont boldSystemFontOfSize:14];[v addSubview:self.statusLabel];
    NSArray *names=@[@"启动测试",@"允许假资料一次",@"读取假资料",@"撤销许可",@"停止"];
    for(NSUInteger i=0;i<names.count;i++){NSButton *b=[NSButton buttonWithTitle:names[i] target:self action:@selector(click:)];b.tag=(NSInteger)i;b.frame=NSMakeRect(25+i*143,307,137,34);[v addSubview:b];}
    NSScrollView *scroll=[[NSScrollView alloc]initWithFrame:NSMakeRect(28,28,704,260)];scroll.hasVerticalScroller=YES;self.output=[[NSTextView alloc]initWithFrame:scroll.bounds];self.output.editable=NO;self.output.font=[NSFont systemFontOfSize:14];scroll.documentView=self.output;[v addSubview:scroll];
    [self show:Result(@"READY_FOR_SYNTHETIC_TEST")];self.refreshTimer=[NSTimer scheduledTimerWithTimeInterval:1 target:self selector:@selector(refreshStatus) userInfo:nil repeats:YES];[self.window makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
}
- (void)refreshStatus {
    NSDictionary *s=Attempt(^{return [self.runner status];});BOOL running=[s[@"running_in_this_process"] boolValue];
    NSDictionary *phases=@{@"idle":@"尚未开始",@"started":@"已开始",@"read_complete":@"已完成一次假资料读取",@"awaiting_resume":@"等待接续"};
    self.statusLabel.stringValue=[NSString stringWithFormat:@"%@  |  假资料许可：%@\n上次任务进度：%@  |  后台辅助进程：0",running?@"当前窗口：已启动":@"当前窗口：未启动 / 已停止",[s[@"usable_in_this_process"] boolValue]?@"可读一次（60秒内）":@"不可读",phases[s[@"task_progress"]]?:@"状态无法确认"];
}
- (void)show:(NSDictionary *)r {
    [self refreshStatus];
    if([r[@"code"] isEqual:@"FIXTURE_READ_OK"])return;
    NSDictionary *zh=@{@"READY_FOR_SYNTHETIC_TEST":@"已打开真实本地程序。点击“启动测试”开始。",@"STARTED":@"测试已启动。默认拒绝读取，尚未授予假资料许可。",@"ALREADY_STARTED":@"当前测试已启动，无需重复启动。",@"TEST_ONLY_GRANTED_ONCE":@"仅允许包内假资料读取一次，有效期60秒。",@"READ_DENIED":@"读取已被拒绝：没有当前有效的一次性测试许可。",@"NOT_RUNNING":@"请先启动测试。",@"REVOKED":@"测试许可已撤销，后续读取将被拒绝。",@"STOPPED_AND_REVOKED":@"测试已停止，许可已撤销。没有后台辅助进程。",@"OTHER_SESSION_ACTIVE_OR_UNKNOWN":@"另一个测试窗口仍在运行，或状态未能确认。本窗口未接管。",@"TEST_AUTHORITY_ALREADY_ACTIVE":@"当前一次性测试许可仍有效，未重复签发。"};
    NSString *text=zh[r[@"code"]]?:[NSString stringWithFormat:@"操作结果：%@",r[@"code"]];
    self.output.string=text;
}
- (void)presentDisclosure:(NSDictionary *)r {
    self.output.string=[NSString stringWithFormat:@"读取成功（仅假资料）\n\n%@\n出处：%@\n版本校验：%@\n\n本次许可已消费，再次读取将被拒绝。",r[@"content"],r[@"citation"],r[@"sha256"]];
}
- (void)click:(NSButton *)b {
    if(b.tag==1){NSAlert *a=[NSAlert new];a.messageText=@"允许读取一次包内假资料？";a.informativeText=@"对象：fixture.md（不含个人知识）\n用途：验证测试包流程\n范围：最多一次读取，60秒有效\n这是测试许可，不是授权读取你的真实资料。";[a addButtonWithTitle:@"允许本次测试"];[a addButtonWithTitle:@"取消"];if([a runModal]!=NSAlertFirstButtonReturn){[self refreshStatus];self.output.string=@"已取消本次许可请求，没有签发新许可。现有测试许可状态见上方。";return;}}
    NSDictionary *r=Attempt(^{switch(b.tag){case 0:return [self.runner start];case 1:return [self.runner grant:60];case 2:return [self.runner readFixture:0];case 3:return [self.runner revoke:NO];default:return [self.runner revoke:YES];}});[self show:r];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)app {(void)app;return YES;}
- (void)applicationWillTerminate:(NSNotification *)n {(void)n;[self.refreshTimer invalidate];if(self.runner.started)Attempt(^{return [self.runner revoke:YES];});}
@end

int main(int argc,const char **argv) {
    @autoreleasepool {
        @try {
            if(argc==2 && strcmp(argv[1],"--sandbox-probe")==0){NSDictionary *p=Probe();PrintJSON(p);return [p[@"actual_restrictions_pass"] boolValue]?0:2;}
            if(argc==2 && strcmp(argv[1],"--inspect")==0){PrintJSON([[XSRunner new]status]);return 0;}
            if(argc==3 && strcmp(argv[1],"--scenario")==0){XSRunner *r=[XSRunner new];r.disclosureSink=^(NSDictionary *d){PrintJSON(d);};PrintJSON(Scenario(r,[NSString stringWithUTF8String:argv[2]]));return 0;}
            if(argc!=1){PrintJSON(Result(@"UNKNOWN_ARGUMENTS"));return 2;}
            NSApplication *app=NSApplication.sharedApplication;[app setActivationPolicy:NSApplicationActivationPolicyRegular];__attribute__((objc_precise_lifetime)) XSApp *delegate=[XSApp new];app.delegate=delegate;[app run];return 0;
        }@catch(NSException *e){PrintJSON(Result([e.name isEqual:@"XSClosed"]?e.reason:@"STARTUP_FAILED_CLOSED"));return 2;}
    }
}
