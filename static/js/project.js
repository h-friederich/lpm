$(document).ready(function() {
  'use strict';

  $(function() {
    $('.data-table').DataTable();
    $('.data-table-nonsorted').DataTable({
      "order": []
    });
  });
});
