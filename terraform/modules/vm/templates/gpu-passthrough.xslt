<?xml version="1.0"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" indent="yes"/>
  
  <!-- Identity transform - copy everything by default -->
  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>
  
  <!-- Add GPU hostdev entries to devices section -->
  <xsl:template match="devices">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
      <!-- GPU passthrough devices will be added here -->
      %{ for idx, pci_addr in gpu_pci_addresses ~}
      <hostdev mode='subsystem' type='pci' managed='yes'>
        <source>
          <address domain='0x0000' bus='0x${split(":", pci_addr)[0]}' slot='0x${split(":", split(".", pci_addr)[0])[1]}' function='0x${split(".", pci_addr)[1]}'/>
        </source>
      </hostdev>
      %{ endfor ~}
    </xsl:copy>
  </xsl:template>
</xsl:stylesheet>
