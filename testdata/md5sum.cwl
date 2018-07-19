cwlVersion: v1.0
class: Workflow

inputs:
  input_file: File

outputs:
  output_file:
    type: File
    outputSource: md5sum/output_file

steps:
  md5sum:
    run: https://raw.githubusercontent.com/common-workflow-language/workflow-service/master/testdata/dockstore-tool-md5sum.cwl
    in:
      input_file: input_file
    out: [output_file]

