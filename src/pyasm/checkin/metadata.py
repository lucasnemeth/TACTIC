###########################################################
#
# Copyright (c) 2005, Southpaw Technology
#                     All Rights Reserved
#
# PROPRIETARY INFORMATION.  This software is proprietary to
# Southpaw Technology, and is not to be reproduced, transmitted,
# or disclosed in any way without written permission.
#
#
#

__all__ = ['CheckinMetadataHandler', 'PILMetadataParser', 'ExifMetadataParser', 'ImageMagickMetadataParser', 'FFProbeMetadataParser']


import os, sys, re, subprocess

from pyasm.common import Common
from pyasm.biz import File

try:
    from PIL import Image
    HAS_PIL = True
    # Test to see if imaging actually works
    import _imaging
except:
    HAS_PIL = False

if Common.which("convert"):
    HAS_IMAGEMAGICK = True
else:
    HAS_IMAGEMAGICK = False

if Common.which("ffprobe"):
    HAS_FFMPEG = True
else:
    HAS_FFMPEG = False


try:
    import exifread
    HAS_EXIF = True
except:
    HAS_EXIF = False



class CheckinMetadataHandler():
    def __init__(my, **kwargs):
        my.kwargs = kwargs

    def execute(my):

        # extra data from the file check-in

        commit = my.kwargs.get("commit")
        if commit in ['false', False]:
            commit = False
        else:
            commit = True

        # metadata can only be associated with a single file on the
        # snapshot.
        files = my.kwargs.get("files")
        file_objects = my.kwargs.get("file_objects")

        snapshot_metadata = None

        for i, file in enumerate(files):
            path = file
            ext = File.get_extension(path)
            file_object = file_objects[i]

            if not os.path.exists(path):
                continue
            elif ext in File.VIDEO_EXT:
                parser_type = "FFMPEG"
            elif ext in File.NORMAL_EXT:
                continue
            else:
                if HAS_IMAGEMAGICK:                    
                    parser_type = "ImageMagick" 
                else:
                    parser_type = "PIL"
            metadata = {}

            if parser_type == "FFMPEG":
                parser = FFProbeMetadataParser(path=path)
                metadata = parser.get_metadata()
            elif parser_type == "ImageMagick":
                parser = ImageMagickMetadataParser(path=path)
                metadata = parser.get_metadata()
            else:
                parser = PILMetadataParser(path=path)
                metadata = parser.get_metadata()

            metadata['__parser__'] = parser_type

            """

            if os.path.exists(path):
                try:
                    parser = ImageMagickMetadataParser(path=path)
                    metadata = parser.get_metadata()
                except:
                    try:
                        #parser = PILMetadataParser(path=path)
                        parser = FFProbeMetadataParser(path=path)
                        metadata = parser.get_metadata()
                    except:
                        metadata = {}
            else:
                metadata = {}
            """

            # add some default metadata
            basename = os.path.basename(path)
            path = file_object.get_lib_path()
            dirname = os.path.dirname(path)
            parts = basename.split(".")
            ext = parts[-1]
            try:
                # occasionally, people will put frame numbers as the last
                # part
                ext = int(ext)
                ext = parts[-2]
            except:
                pass

            metadata['Ext'] = ext
            metadata['Basename'] = basename
            metadata['Dirname'] = dirname


            if metadata and not file_object.get_value("metadata"):
                file_object.add_metadata(metadata, replace=True)
                searchable = my.get_searchable(metadata)
                file_object.set_value("metadata_search", searchable)

                file_object.commit()


                if i == 0:
                    snapshot = my.kwargs.get("snapshot")
                    snapshot.add_metadata(metadata, replace=True)
                    if commit:
                        snapshot.commit()



    def get_searchable(my, metadata):
        pairs = []
        pairs_set = set()
        for name, value in metadata.items():
            # get rid of the spaces
            if name == "__keys__":
                continue

            # ignore attributes that are numbers only
            try:
                name = int(name)
                continue
            except:
                pass

            # clean up the names for indexed searching
            name = name.lower()
            name = name.replace(" ", "_")
            name = name.replace(":", "_")
            
            keys = [] 
            # otherwise it could an int or float
            if isinstance(value, basestring):
                value = value.lower()
                value = value.replace("(", "")
                value = value.replace(")", "")
                value = value.replace(" ", "_")
                keys = value.split(" ")
            
            if len(keys) > 1:
                for key in keys:
                    pair = "%s=%s" % (name, key)
                    if pair in pairs_set:
                        continue
                    pairs.append(pair)
                    pairs_set.add(pair)

            
            pair = "%s=%s" % (name, value)
            pairs.append(pair)



        searchable = " ".join(pairs)

        return searchable



#
# Common file types
#
#from PIL import Image
#from PIL.ExifTags import TAGS

class BaseMetadataParser(object):
    def __init__(my, **kwargs):
        my.kwargs = kwargs

    def get_media_type(my):
        return "image"

    def get_metadata(my):
        return {}

    def get_tactic_mapping(my):
        return {}


    def get_initial_data(my):
        return {
        }

    def get_tactic_metadata(my):

        tactic_data = my.get_initial_data()

        metadata = my.get_metadata()

        mapping = my.get_tactic_mapping()
        for name, name2 in mapping.items():
            tactic_data[name] = metadata.get(name2)

        return tactic_data
    
    def sanitize_data(my, data):
        # sanitize output
        RE_ILLEGAL_XML = u'([\u0000-\u0008\u000b-\u000c\u000e-\u001f\ufffe-\uffff])' + \
                 u'|' + u'([%s-%s][^%s-%s])|([^%s-%s][%s-%s])|([%s-%s]$)|(^[%s-%s])' % \
                  (unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff),
                   unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff),
                   unichr(0xd800),unichr(0xdbff),unichr(0xdc00),unichr(0xdfff))
        data = re.sub(RE_ILLEGAL_XML, "?", data)
        return data
    
    



class PILMetadataParser(BaseMetadataParser):

    def __init__(my, **kwargs):
        my.kwargs = kwargs

    def get_initial_data(my):
        return {
            'media_type': 'image',
            'parser': 'PIL'
        }

    def get_metadata(my):
        path = my.kwargs.get("path")

        try:
            from PIL import Image
            im = Image.open(path)
            return my._get_data(im)
        except Exception, e:
            print "WARNING: ", e
            return {}

 
    def _get_data(my, im):
        #info = im._getexif()
        ret = {}
        #if info:
        #    for tag, value in info.items():
        #        decoded = TAGS.get(tag, tag)
        #        ret[decoded] = value

        size = im.size
        ret['width'] = size[0]
        ret['height'] = size[1]
        ret['format'] = im.format
        ret['format_description'] = im.format_description

        return ret


    def get_tactic_mapping(my):
        return {
            'width': 'width',
            'height': 'height',
            'format': 'format',
            'format_description': 'format_description'
        }




class ExifMetadataParser(BaseMetadataParser):

    def __init__(my, **kwargs):
        my.kwargs = kwargs


    def get_initial_data(my):
        return {
            'media_type': 'image',
            'parser': 'Exif'
        }



    def get_metadata(my):
        path = my.kwargs.get("path")

        from pyasm.checkin import exifread
        #import exifread

        f = open(path)
        tags = exifread.process_file(f)

        return tags




class ImageMagickMetadataParser(BaseMetadataParser):

    def __init__(my, **kwargs):
        my.kwargs = kwargs

    def get_initial_data(my):
        return {
            'media_type': 'image',
            'parser': 'ImageMagick'
        }

    def get_metadata(my):
        path = my.kwargs.get("path")

        import subprocess, re

        ret = {}

        process = subprocess.Popen(['identify','-verbose', path], shell=False, stdout=subprocess.PIPE)
        ret_val, error = process.communicate()
        if error:
            return ret

        ret_val = my.sanitize_data(ret_val)
        p = re.compile(":\ +")

        level = 0
        names = []
        curr_ret = ret
        for line in ret_val.split("\n"):
            line = line.strip()
            if not line:
                continue

            index = 0
            while 1:
                if index >= len(line):
                    break
                if line[index] != ' ':
                    break
                index += 1
            level = index / 2
            line = line.strip()

            if not line:
                continue

            if line.endswith(":"):
                name = line.rstrip(":")
                curr_ret = {}
                ret[name] = "None"
                continue

            parts = re.split(p, line)
            if len(parts) < 2:
                print "WARNING: Skipping an ImageMagick line [%s] due to inconsistent formatting." % line
                continue
            name = parts[0]
            value = parts[1]
            try:
                if isinstance(value, unicode):
                   value = value.encode('utf-8', 'ignore')
                else:
                   value = unicode(value, errors='ignore').encode('utf-8')

                ret[name] = value
                names.append(name)
            except Exception, e:
                print "WARNING: Cannot handle line [%s] with error: " % line, e


        if names:
            ret['__keys__'] = names


        return ret



class FFProbeMetadataParser(BaseMetadataParser):
    def __init__(my, **kwargs):
        my.kwargs = kwargs

    def get_initial_data(my):
        return {
            'media_type': 'video',
            'parser': 'FFProbe'
        }

    def get_metadata(my):
        path = my.kwargs.get("path")
        
        try:
            out = my.probe_file(path)
        except:
            out = ''

        # sanitize output
        
        out = my.sanitize_data(out)

        metadata = my.parse_output(out)

        return metadata

        
        


    def probe_file(my, fpath):
        cmd = ['ffprobe', '-show_streams', '-pretty', '-loglevel', 'quiet', fpath]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        return out 


    def parse_output(my, out):

        index = 0
        metadata_list = {}

        metadata = {}


        for line in out.split("\n"):
            if line.find("STREAM") != -1:
                continue
            if not line:
                continue

            line = line.strip()
            parts = line.split("=")
            name = parts[0]
            value = parts[1]

            if name == "index":
                index = value
                data = {}

            elif name == "codec_type":
                metadata[value] = data

            data[str(name)] = str(value)

        flat_metadata = {}
        for prefix, data in metadata.items():
            for name, value in data.items():
                key = "%s:%s" % (prefix, name)
                flat_metadata[key] = value

        return flat_metadata


    def get_tactic_mapping(my):
        return {
            'width': 'video:width',
            'height': 'video:height',
            'frames': 'video:nb_frames',
            'fps': 'video:r_frame_rate',
            'codec': 'video:codec_name'
        }




if __name__ == '__main__':
    import sys
    import tacticenv
    parser = FFProbeMetadataParser(path=sys.argv[1])
    metadata = parser.get_metadata()
    from pyasm.common import Common
    Common.pretty_print(metadata)

