function dcac_write_json(path,data)
%DCAC_WRITE_JSON Write UTF-8 JSON and close the file on all code paths.
fid = fopen(path,'w','n','UTF-8');
if fid < 0, error('DCAC:IO','Cannot write JSON: %s',path); end
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s',jsonencode(data));
end
