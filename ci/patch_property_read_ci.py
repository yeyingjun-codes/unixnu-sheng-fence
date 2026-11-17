from pathlib import Path
import sys

# Patch NativeAdrenoPublish.cpp in the CI build tree with a read-only ring
# of the newest eight registry-property reads (key + process + pid).
# Usage: python3 patch_property_read_ci.py <path-to-NativeAdrenoPublish.cpp>

path = Path(sys.argv[1])
text = path.read_text()

anchor = '''/* Processes that read MetalPluginName (the Metal discovery), first twelve names, with counts. */
struct NativeAdrenoAskerRecord {char name[20]; uint32_t reads;};
struct NativeAdrenoAskerRecord native_adreno_metal_askers[12];'''
addition = anchor + '''
/* The newest eight registry-property reads (read-only): process, pid and key, so a later report
 * can tell whether backboardd ever reaches property discovery before it opens the accelerator. */
struct NativeAdrenoPropertyRecord {char key[32]; char name[20]; int32_t pid; uint32_t sequence;};
struct NativeAdrenoPropertyRecord native_adreno_property_read_log[8];
volatile uint32_t native_adreno_property_read_log_count;'''
if text.count(anchor) != 1:
    raise SystemExit('metal asker anchor not found')
text = text.replace(anchor, addition, 1)

old = '''extern "C" void native_adreno_note_property_read(const char *key)
{
    if(key && !strcmp(key,"MetalPluginName")) {
        proc_selfname(native_adreno_metal_diag.name_reader,17);
        native_adreno_metal_diag.name_reads=native_adreno_metal_diag.name_reads+1;
        char name[20]={};
        proc_selfname(name,sizeof name);
        /* Unlocked: the discovery runs at process start, a lost count is harmless and a row is claimed by its first byte. */
        for(auto &asker:native_adreno_metal_askers) {
            if(!asker.name[0]) {strlcpy(asker.name,name,sizeof asker.name);asker.reads=1;break;}
            if(!strncmp(asker.name,name,sizeof asker.name)) {asker.reads=asker.reads+1;break;}
        }
    }
    shiftName(native_adreno_metal_diag.reader);
    native_adreno_metal_diag.property_reads=native_adreno_metal_diag.property_reads+1;
}'''
new = '''extern "C" void native_adreno_note_property_read(const char *key)
{
    if(key && !strcmp(key,"MetalPluginName")) {
        proc_selfname(native_adreno_metal_diag.name_reader,17);
        native_adreno_metal_diag.name_reads=native_adreno_metal_diag.name_reads+1;
        char name[20]={};
        proc_selfname(name,sizeof name);
        /* Unlocked: the discovery runs at process start, a lost count is harmless and a row is claimed by its first byte. */
        for(auto &asker:native_adreno_metal_askers) {
            if(!asker.name[0]) {strlcpy(asker.name,name,sizeof asker.name);asker.reads=1;break;}
            if(!strncmp(asker.name,name,sizeof asker.name)) {asker.reads=asker.reads+1;break;}
        }
    }
    shiftName(native_adreno_metal_diag.reader);
    native_adreno_metal_diag.property_reads=native_adreno_metal_diag.property_reads+1;
    {
        const uint32_t sequence=native_adreno_property_read_log_count+1;
        NativeAdrenoPropertyRecord &record=native_adreno_property_read_log[sequence&7];
        strlcpy(record.key,key?key:"",sizeof record.key);
        proc_selfname(record.name,sizeof record.name);
        record.pid=proc_selfpid();
        record.sequence=sequence;
        native_adreno_property_read_log_count=sequence;
    }
}'''
if text.count(old) != 1:
    raise SystemExit('property-read function anchor not found')
text = text.replace(old, new, 1)

path.write_text(text)
print('patched property-read ring in', path)
