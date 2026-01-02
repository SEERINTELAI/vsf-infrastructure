{{/*
Expand the name of the chart.
*/}}
{{- define "mock-dcgm-exporter.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "mock-dcgm-exporter.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "mock-dcgm-exporter.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "mock-dcgm-exporter.labels" -}}
helm.sh/chart: {{ include "mock-dcgm-exporter.chart" . }}
{{ include "mock-dcgm-exporter.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
vsf/mock-mode: "true"
{{- end }}

{{/*
Selector labels
*/}}
{{- define "mock-dcgm-exporter.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mock-dcgm-exporter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
