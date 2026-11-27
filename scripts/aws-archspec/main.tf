terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

variable "instance_file" {
  type = string
  default = "instances.csv"
}

locals {
  instances = csvdecode(file(var.instance_file))
}


resource "aws_security_group" "archspec_sg" {
  name        = "archspec_sg"
  description = "Security Group for Archspec Test Boxes"

  ingress {
    description      = "SSH"
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    "Built_By": "Terraform",
    "Project": "MEVA"
  }
}




resource "aws_instance" "cluster_boxes" {
  for_each = {for inst in local.instances : inst.local_id => inst }

  instance_type = each.value.instance_type
  ami = each.value.ami
  key_name = "archspec-service-account"
  associate_public_ip_address = true
  # TODO security group with IP lockdown
  security_groups = [aws_security_group.archspec_sg.name]

  user_data = <<EOF
#!/bin/bash

sudo pip3 install archspec
ARCHSPEC=$(/usr/local/bin/archspec cpu)
echo "${each.value.local_id},${each.value.instance_type},${each.value.ami},$ARCHSPEC" | sudo tee -a /instance.txt

EOF

  tags = {
    "Name": "Archspec Test Box (${each.value.local_id})",
    "Built_By": "Terraform"
  }

}

resource "local_file" "sshloginfile" {
  content = <<EOF
%{ for local_id, inst in aws_instance.cluster_boxes ~}
${inst.public_ip}
%{ endfor ~}
EOF
  filename = "./cluster"
  file_permission = "0640"
}


output "instance_ids" {
  value = values(aws_instance.cluster_boxes)[*].id
}
